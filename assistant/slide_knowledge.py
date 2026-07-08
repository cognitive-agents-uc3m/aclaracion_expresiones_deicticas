import gc
import hashlib
import json
import logging
import os
import queue
import sqlite3
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from .settings import settings
from .slide_layout import extract_slide_elements_from_page, format_elements_inventory, elements_to_json, elements_from_json

logger = logging.getLogger(__name__)

SPATIAL_TOKENS = [
    "izquierda", "derecha", "arriba", "abajo", "centro", "superior", "inferior",
]

def _knowledge_profile_tag() -> str:
    profile = str(getattr(settings, "ACTIVE_SLIDE_PROMPT_PROFILE", "ESTADISTICA") or "ESTADISTICA").strip() or "ESTADISTICA"
    tag = f"p{profile}"
    fmt = str(getattr(settings, "slide_description_format", "text") or "text").strip().lower()
    if fmt == "html":
        tag = f"{tag}:fHTML"
    return tag

class SlideKnowledgeStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._db_path = settings.slide_knowledge_db_path
        self._file_hash_cache: Dict[str, Tuple[int, int, str]] = {}

        db_dir = os.path.dirname(os.path.abspath(self._db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS presentations (
                        deck_id TEXT PRIMARY KEY,
                        pdf_path TEXT NOT NULL,
                        file_hash TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_mtime INTEGER NOT NULL,
                        slide_count INTEGER NOT NULL,
                        knowledge_version INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS slides (
                        deck_id TEXT NOT NULL,
                        slide_index INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        detailed_description TEXT,
                        summary TEXT,
                        spatial_mentions TEXT,
                        elements_json TEXT,
                        error TEXT,
                        vision_model TEXT,
                        knowledge_version INTEGER NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (deck_id, slide_index),
                        FOREIGN KEY (deck_id) REFERENCES presentations(deck_id) ON DELETE CASCADE
                    )
                    """
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_presentations_file_hash ON presentations(file_hash)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_slides_status ON slides(deck_id, status)"
                )
                cols = {
                    row["name"]
                    for row in self._conn.execute("PRAGMA table_info(slides)").fetchall()
                }
                if "elements_json" not in cols:
                    self._conn.execute("ALTER TABLE slides ADD COLUMN elements_json TEXT;")

    def _hash_file(self, abs_path: str) -> str:
        hasher = hashlib.sha256()
        with open(abs_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def _compute_file_fingerprint(self, pdf_path: str) -> Tuple[str, int, int, str]:
        abs_path = os.path.abspath(pdf_path)
        stat = os.stat(abs_path)
        size = int(stat.st_size)
        mtime = int(stat.st_mtime)

        cached = self._file_hash_cache.get(abs_path)
        if cached and cached[0] == size and cached[1] == mtime:
            return abs_path, size, mtime, cached[2]

        file_hash = self._hash_file(abs_path)
        self._file_hash_cache[abs_path] = (size, mtime, file_hash)
        return abs_path, size, mtime, file_hash

    def deck_id_from_pdf(self, pdf_path: str) -> str:
        _, _, _, file_hash = self._compute_file_fingerprint(pdf_path)
        return f"{file_hash}:v{int(settings.slide_knowledge_version)}:{_knowledge_profile_tag()}"

    def ensure_deck(self, pdf_path: str, slide_count: int) -> str:
        abs_path, size, mtime, file_hash = self._compute_file_fingerprint(pdf_path)
        deck_id = f"{file_hash}:v{int(settings.slide_knowledge_version)}:{_knowledge_profile_tag()}"
        now = time.time()

        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO presentations (
                        deck_id, pdf_path, file_hash, file_size, file_mtime,
                        slide_count, knowledge_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(deck_id) DO UPDATE SET
                        pdf_path=excluded.pdf_path,
                        file_size=excluded.file_size,
                        file_mtime=excluded.file_mtime,
                        slide_count=excluded.slide_count,
                        updated_at=excluded.updated_at
                    """,
                    (deck_id, abs_path, file_hash, size, mtime, int(slide_count),
                     int(settings.slide_knowledge_version), now, now),
                )
        return deck_id

    def update_slide(
        self,
        deck_id: str,
        slide_index: int,
        status: str,
        detailed_description: Optional[str] = None,
        summary: Optional[str] = None,
        spatial_mentions: Optional[List] = None,
        elements: Optional[List] = None,
        error: Optional[str] = None,
        vision_model: Optional[str] = None,
    ) -> None:
        now = time.time()
        mentions_json = json.dumps(spatial_mentions or [], ensure_ascii=False)
        elements_json = elements_to_json(elements or [])
        model_name = vision_model or settings.vision_model_name

        with self._lock:
            with self._conn:
                exists = self._conn.execute(
                    "SELECT 1 FROM presentations WHERE deck_id = ?", (deck_id,)
                ).fetchone()
                if not exists:
                    return
                self._conn.execute(
                    """
                    INSERT INTO slides (
                        deck_id, slide_index, status, detailed_description, summary,
                        spatial_mentions, elements_json, error, vision_model, knowledge_version, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(deck_id, slide_index) DO UPDATE SET
                        status=excluded.status,
                        detailed_description=excluded.detailed_description,
                        summary=excluded.summary,
                        spatial_mentions=excluded.spatial_mentions,
                        elements_json=excluded.elements_json,
                        error=excluded.error,
                        vision_model=excluded.vision_model,
                        knowledge_version=excluded.knowledge_version,
                        updated_at=excluded.updated_at
                    """,
                    (deck_id, int(slide_index), status, detailed_description, summary,
                     mentions_json, elements_json, error, model_name,
                     int(settings.slide_knowledge_version), now),
                )

    def get_slide(self, deck_id: str, slide_index: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT status, detailed_description, summary, spatial_mentions, elements_json, error,
                       vision_model, knowledge_version, updated_at
                FROM slides
                WHERE deck_id = ? AND slide_index = ?
                """,
                (deck_id, int(slide_index)),
            ).fetchone()

        if not row:
            return None

        spatial_mentions: List = []
        raw_mentions = row["spatial_mentions"]
        if raw_mentions:
            try:
                loaded = json.loads(raw_mentions)
                if isinstance(loaded, list):
                    spatial_mentions = loaded
            except Exception:
                pass

        return {
            "status": row["status"],
            "detailed_description": row["detailed_description"],
            "summary": row["summary"],
            "spatial_mentions": spatial_mentions,
            "elements": elements_from_json(row["elements_json"]),
            "error": row["error"],
            "vision_model": row["vision_model"],
            "knowledge_version": row["knowledge_version"],
            "updated_at": row["updated_at"],
        }

    def get_slide_by_pdf(self, pdf_path: str, slide_index: int) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        if not pdf_path or not os.path.exists(pdf_path):
            return None, None
        try:
            deck_id = self.deck_id_from_pdf(pdf_path)
        except Exception:
            return None, None
        return deck_id, self.get_slide(deck_id, slide_index)

    def get_deck_progress(self, deck_id: str) -> Tuple[int, int, int, int]:
        with self._lock:
            deck_row = self._conn.execute(
                "SELECT slide_count FROM presentations WHERE deck_id = ?", (deck_id,)
            ).fetchone()
            if not deck_row:
                return 0, 0, 0, 0

            total = int(deck_row["slide_count"])
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS c FROM slides WHERE deck_id = ? GROUP BY status",
                (deck_id,),
            ).fetchall()

        done = failed = processing = 0
        for row in rows:
            count = int(row["c"])
            if row["status"] == "ready":
                done += count
            elif row["status"] == "error":
                failed += count
            elif row["status"] == "processing":
                processing += count
        return done, total, failed, processing

    def get_deck_progress_by_pdf(self, pdf_path: Optional[str]) -> Tuple[int, int, int, int]:
        if not pdf_path or not os.path.exists(pdf_path):
            return 0, 0, 0, 0
        try:
            deck_id = self.deck_id_from_pdf(pdf_path)
        except Exception:
            return 0, 0, 0, 0
        return self.get_deck_progress(deck_id)

    def deck_progress_percent(self, pdf_path: Optional[str]) -> float:
        done, total, failed, _ = self.get_deck_progress_by_pdf(pdf_path)
        if total <= 0:
            return 0.0
        return round((min(total, done + failed) / float(total)) * 100.0, 1)

    def deck_status_text(self, pdf_path: Optional[str]) -> str:
        if not pdf_path or not os.path.exists(pdf_path):
            return "Preproceso: sin PDF."
        done, total, failed, processing = self.get_deck_progress_by_pdf(pdf_path)
        pending = max(0, total - done - failed - processing)
        pct = self.deck_progress_percent(pdf_path)
        return (
            f"Preproceso: {pct:.1f}% | listas {done}/{total}, "
            f"procesando {processing}, pendientes {pending}, error {failed}."
        )

def _extract_spatial_mentions(text: str) -> List[str]:
    lowered = (text or "").lower()
    return [token for token in SPATIAL_TOKENS if token in lowered]

def _looks_like_timeout_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    return any(t in lowered for t in ("timeout", "timed out", "readtimeout", "deadline exceeded"))

class SlidePrecomputeService:
    def __init__(self):
        self._queue: "queue.Queue[Tuple[str, int, str]]" = queue.Queue(maxsize=8)
        self._inflight: set = set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def enqueue_pdf(self, pdf_path: str, slide_count: int, mode: str = "all") -> Optional[str]:
        if not pdf_path or not os.path.exists(pdf_path):
            return None
        mode = (mode or "all").strip().lower()
        if mode not in {"all", "errors"}:
            mode = "all"

        deck_id = slide_knowledge_store.ensure_deck(pdf_path, slide_count)
        with self._lock:
            if deck_id in self._inflight:
                return deck_id
            self._inflight.add(deck_id)
        try:
            self._queue.put_nowait((pdf_path, int(slide_count), mode))
        except queue.Full:
            with self._lock:
                self._inflight.discard(deck_id)
        return deck_id

    def enqueue_retry_errors(self, pdf_path: str, slide_count: int) -> Optional[str]:
        return self.enqueue_pdf(pdf_path, slide_count, mode="errors")

    def is_pdf_inflight(self, pdf_path: Optional[str]) -> bool:
        if not pdf_path or not os.path.exists(pdf_path):
            return False
        try:
            deck_id = slide_knowledge_store.deck_id_from_pdf(pdf_path)
        except Exception:
            return False
        with self._lock:
            return deck_id in self._inflight

    def _worker_loop(self) -> None:
        while True:
            pdf_path = None
            deck_id = None
            task_taken = False
            try:
                pdf_path, slide_count, mode = self._queue.get()
                task_taken = True
                if not os.path.exists(pdf_path):
                    logger.warning("[Precompute] PDF no encontrado: %s", pdf_path)
                    continue

                deck_id = slide_knowledge_store.ensure_deck(pdf_path, slide_count)
                logger.info(
                    "[Precompute] Inicio deck=%s mode=%s slides=%d pdf=%s",
                    deck_id[:12], mode, slide_count, pdf_path,
                )
                logger.info(
                    "[Precompute] Config: vision_timeout=%ss | retries=%s | backoff=%ss | "
                    "inter_slide_delay=%ss | cooldown_every=%s | cooldown_seconds=%ss",
                    settings.precompute_slide_timeout_seconds,
                    settings.precompute_retry_attempts,
                    settings.precompute_retry_backoff_seconds,
                    settings.precompute_inter_slide_delay_seconds,
                    settings.precompute_cooldown_every_n_slides,
                    settings.precompute_cooldown_seconds,
                )

                from .nodes import generate_slide_knowledge_for_image
                from .slide_html import generate_slide_html_for_page
                import fitz

                use_html = str(getattr(settings, "slide_description_format", "text") or "text").strip().lower() == "html"
                model_label = settings.slide_html_model if use_html else None
                logger.info("[Precompute] Formato de descripcion: %s", "html" if use_html else "text")

                with fitz.open(pdf_path) as doc:
                    count = doc.page_count
                    processed_in_run = 0
                    vision_last_end_ts = 0.0
                    continuous_vision_seconds = 0.0

                    for slide_index in range(count):
                        out_path = None
                        existing = slide_knowledge_store.get_slide(deck_id, slide_index)
                        status = (existing or {}).get("status")
                        if mode == "errors" and status != "error":
                            continue
                        if mode == "all" and status == "ready":
                            continue

                        try:
                            logger.info("[Precompute] Procesando slide %d/%d...", slide_index + 1, count)
                            slide_knowledge_store.update_slide(deck_id, slide_index, status="processing")

                            t0 = time.time()
                            page = doc.load_page(slide_index)
                            logger.debug("[Precompute]  - page.load_page OK en %.2fs", time.time() - t0)

                            layout = extract_slide_elements_from_page(page)
                            elements = layout.get("elements") or []
                            inventory_text = format_elements_inventory(elements)

                            if not use_html:
                                t1 = time.time()
                                pix = page.get_pixmap(
                                    matrix=fitz.Matrix(settings.precompute_render_scale, settings.precompute_render_scale),
                                    alpha=False,
                                )
                                logger.debug("[Precompute]  - pixmap OK en %.2fs | size=%dx%d", time.time() - t1, pix.width, pix.height)

                                digest = hashlib.md5(f"{deck_id}:{slide_index}".encode("utf-8")).hexdigest()
                                out_path = os.path.join(tempfile.gettempdir(), f"agenda2030_precompute_{digest}.png")

                                t2 = time.time()
                                pix.save(out_path)
                                file_size = os.path.getsize(out_path) if os.path.exists(out_path) else -1
                                logger.debug("[Precompute]  - save OK en %.2fs | path=%s | bytes=%d", time.time() - t2, out_path, file_size)

                            min_gap = max(0.0, float(settings.precompute_min_seconds_between_vision_calls))
                            if min_gap > 0 and vision_last_end_ts > 0:
                                wait_s = max(0.0, min_gap - (time.time() - vision_last_end_ts))
                                if wait_s > 0:
                                    logger.debug("[Precompute]  - enfriando %.2fs antes de invocar vision.", wait_s)
                                    time.sleep(wait_s)

                            t3 = time.time()
                            if use_html:
                                logger.info("[Precompute]  - html START slide %d/%d", slide_index + 1, count)
                                detailed, summary = generate_slide_html_for_page(
                                    doc,
                                    slide_index=slide_index,
                                    slide_count=count,
                                )
                            else:
                                logger.info("[Precompute]  - vision START slide %d/%d", slide_index + 1, count)
                                detailed, summary = generate_slide_knowledge_for_image(
                                    image_path=out_path,
                                    slide_index=slide_index,
                                    slide_count=count,
                                )
                            detailed = (detailed or "").strip()
                            if inventory_text and "[Inventario por bounding boxes]" not in detailed:
                                detailed = f"{detailed}\n\n{inventory_text}".strip()
                            vision_elapsed = time.time() - t3
                            vision_last_end_ts = time.time()
                            continuous_vision_seconds += vision_elapsed
                            logger.info("[Precompute]  - vision END en %.2fs", vision_elapsed)

                            summary_log = (" ".join((summary or "").split()) or "Sin resumen.")[:320]
                            logger.info("[Precompute]  - resumen slide %d/%d: %s", slide_index + 1, count, summary_log)
                            detail_log = (detailed or "Sin descripcion detallada.").strip()
                            if use_html and len(detail_log) > 600:
                                detail_log = f"{detail_log[:600]}... [{len(detailed)} chars]"
                            logger.info("[Precompute]  - descripcion slide %d/%d:\n%s", slide_index + 1, count, detail_log)

                            slide_knowledge_store.update_slide(
                                deck_id, slide_index,
                                status="ready",
                                detailed_description=detailed,
                                summary=summary,
                                spatial_mentions=_extract_spatial_mentions(detailed),
                                elements=elements,
                                vision_model=model_label,
                            )
                            logger.info("[Precompute] Slide %d/%d lista.", slide_index + 1, count)
                            processed_in_run += 1

                            vision_budget = max(0.0, float(settings.precompute_vision_work_budget_seconds))
                            budget_cooldown = max(0.0, float(settings.precompute_budget_cooldown_seconds))
                            if vision_budget > 0 and budget_cooldown > 0 and continuous_vision_seconds >= vision_budget:
                                logger.info(
                                    "[Precompute] Cooldown por presupuesto de vision (%.1fs acumulados) durante %.1fs.",
                                    continuous_vision_seconds, budget_cooldown,
                                )
                                time.sleep(budget_cooldown)
                                continuous_vision_seconds = 0.0

                        except Exception as ex:
                            err = f"{type(ex).__name__}: {ex}"
                            slide_knowledge_store.update_slide(deck_id, slide_index, status="error", error=err)
                            logger.error("[Precompute] Error en slide %d/%d: %s", slide_index + 1, count, err)
                            processed_in_run += 1

                            if _looks_like_timeout_error(err):
                                timeout_cooldown = max(0.0, float(settings.precompute_timeout_cooldown_seconds))
                                if timeout_cooldown > 0:
                                    logger.info("[Precompute] Timeout detectado. Cooldown extra de %.1fs.", timeout_cooldown)
                                    time.sleep(timeout_cooldown)
                                    continuous_vision_seconds = 0.0
                        finally:
                            try:
                                if out_path and os.path.exists(out_path):
                                    os.remove(out_path)
                            except Exception:
                                pass
                            gc.collect()

                            inter_delay = max(0.0, float(settings.precompute_inter_slide_delay_seconds))
                            if inter_delay > 0:
                                time.sleep(inter_delay)

                            cooldown_every = int(settings.precompute_cooldown_every_n_slides)
                            cooldown_seconds = max(0.0, float(settings.precompute_cooldown_seconds))
                            if (
                                cooldown_every > 0
                                and processed_in_run > 0
                                and (processed_in_run % cooldown_every == 0)
                                and cooldown_seconds > 0
                            ):
                                logger.info(
                                    "[Precompute] Cooldown tras %d slides (%.1fs) para evitar saturacion.",
                                    processed_in_run, cooldown_seconds,
                                )
                                time.sleep(cooldown_seconds)

            except Exception as ex:
                logger.error("[Precompute] Error en worker: %s: %s", type(ex).__name__, ex)
            finally:
                if deck_id:
                    with self._lock:
                        self._inflight.discard(deck_id)
                    logger.info("[Precompute] Fin deck=%s", deck_id[:12])
                if task_taken:
                    self._queue.task_done()

slide_knowledge_store = SlideKnowledgeStore()
slide_precompute_service = SlidePrecomputeService()