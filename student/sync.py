import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import fitz
from langchain_core.messages import HumanMessage
from assistant.settings import settings
from assistant.slide_knowledge import slide_knowledge_store, slide_precompute_service
from assistant.slide_render import SlideRenderCache

logger = logging.getLogger(__name__)

class RemoteDeckSync:

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.remote_url: Optional[str] = None
        self.session_key: Optional[str] = None
        self.local_pdf_path: Optional[str] = None
        self.final_pdf_path: Optional[str] = None
        self.notes_pdf_path: Optional[str] = None
        self.current_slide_index = 0
        self.current_slide_count = 0
        self.pointer_x_norm: Optional[float] = None
        self.pointer_y_norm: Optional[float] = None
        self.pointer_ts_ms: Optional[int] = None
        self.remote_status = "Sin conexion."
        self.precompute_status = "Preproceso: sin PDF."
        self._pdf_token: Optional[str] = None
        self._final_pdf_token: Optional[str] = None
        self._final_pdf_last_attempt_ns = 0
        self.final_pdf_status = "PDF final: pendiente."
        self.student_notes = ""
        self._notes_pdf_token: Optional[str] = None
        self._notes_pdf_last_attempt_ns = 0
        self.notes_pdf_status = "PDF notas alumno: pendiente."
        self.notes_format_status = "Formateo notas: pendiente."
        self._notes_formatted_token: Optional[str] = None
        self._notes_formatted_text: Optional[str] = None
        self._notes_format_last_attempt_ns = 0
        self._notes_formatter_llm: Any = None
        self._log_final_pdf_token: Optional[str] = None
        self._log_notes_pdf_token: Optional[str] = None
        self._log_format_token: Optional[str] = None
        self._log_both_saved_token: Optional[str] = None
        self._notes_export_inflight_token: Optional[str] = None
        self._last_sync_error: Optional[str] = None
        self._last_notes_edit_ns = 0
        self._pending_marker_slide_index: Optional[int] = None
        self._last_slide_index_seen: Optional[int] = None
        self._notes_ever_written = False
        self._last_teacher_seq = 0
        self._pending_teacher_text: Optional[str] = None
        self._last_clarification_seq = 0
        self._pending_clarification: Optional[str] = None
        self._renderer = SlideRenderCache("agenda2030_student_local")
        self._cache_dir = os.path.join(tempfile.gettempdir(), "agenda2030_student_local")
        os.makedirs(self._cache_dir, exist_ok=True)

    def __getstate__(self) -> dict:
        state = dict(self.__dict__)
        state["lock"] = None
        state["_notes_formatter_llm"] = None
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state or {})
        self.lock = threading.Lock()
        if not getattr(self, "_cache_dir", None):
            self._cache_dir = os.path.join(tempfile.gettempdir(), "agenda2030_student_local")
        os.makedirs(self._cache_dir, exist_ok=True)
        if not isinstance(getattr(self, "_renderer", None), SlideRenderCache):
            self._renderer = SlideRenderCache("agenda2030_student_local")

        _defaults = (
            ("notes_pdf_path", None),
            ("notes_pdf_status", "PDF notas alumno: pendiente."),
            ("notes_format_status", "Formateo notas: pendiente."),
            ("pointer_x_norm", None),
            ("pointer_y_norm", None),
            ("pointer_ts_ms", None),
            ("_notes_formatted_token", None),
            ("_notes_formatted_text", None),
            ("_notes_format_last_attempt_ns", 0),
            ("_notes_formatter_llm", None),
            ("_log_final_pdf_token", None),
            ("_log_notes_pdf_token", None),
            ("_log_format_token", None),
            ("_log_both_saved_token", None),
            ("_notes_export_inflight_token", None),
            ("_last_sync_error", None),
            ("_last_notes_edit_ns", 0),
            ("_pending_marker_slide_index", None),
            ("_last_slide_index_seen", None),
            ("_notes_ever_written", False),
            ("_last_clarification_seq", 0),
            ("_pending_clarification", None),
        )
        for name, default in _defaults:
            if name not in self.__dict__:
                setattr(self, name, default)
            elif getattr(self, name, None) is None and default is not None:
                setattr(self, name, default)

    def configure(self, session_key: str) -> str:
        base = settings.student_remote_url.rstrip("/")
        key = (session_key or "").strip()
        if not key:
            return "Debes indicar la clave de sesión."
        if not base:
            return "URL del profesor no configurada."

        with self.lock:
            self.remote_url = base
            self.session_key = key
            self._last_teacher_seq = 0
            self._pending_teacher_text = None
            self._last_clarification_seq = 0
            self._pending_clarification = None
            self._final_pdf_token = None
            self.final_pdf_path = None
            self._final_pdf_last_attempt_ns = 0
            self.final_pdf_status = "PDF final: pendiente."
            self.pointer_x_norm = None
            self.pointer_y_norm = None
            self.pointer_ts_ms = None
            self.student_notes = ""
            self._notes_pdf_token = None
            self.notes_pdf_path = None
            self._notes_pdf_last_attempt_ns = 0
            self.notes_pdf_status = "PDF notas alumno: pendiente."
            self.notes_format_status = "Formateo notas: pendiente."
            self._notes_formatted_token = None
            self._notes_formatted_text = None
            self._notes_format_last_attempt_ns = 0
            self._notes_formatter_llm = None
            self._log_final_pdf_token = None
            self._log_notes_pdf_token = None
            self._log_format_token = None
            self._log_both_saved_token = None
            self._notes_export_inflight_token = None
            self._last_sync_error = None
            self._last_notes_edit_ns = 0
            self._pending_marker_slide_index = None
            self._last_slide_index_seen = None
            self._notes_ever_written = False

        ok, msg = self.sync(force_pdf=True)
        return msg if ok else f"Error de conexion: {msg}"

    def set_student_notes_raw(self, notes: str) -> None:
        now_ns = time.time_ns()
        with self.lock:
            self.student_notes = notes or ""
            self._last_notes_edit_ns = now_ns
            if (self.student_notes or "").strip():
                self._notes_ever_written = True

    def set_student_notes(self, notes: str, marker_idle_seconds: float = 2.0) -> Optional[str]:
        new_notes = notes or ""
        now_ns = time.time_ns()
        idle_ns = int(float(marker_idle_seconds) * 1_000_000_000)

        with self.lock:
            old = self.student_notes or ""
            if new_notes == old:
                return None

            pending = self._pending_marker_slide_index
            last_edit_ns = int(self._last_notes_edit_ns or 0)
            has_been_idle = (last_edit_ns == 0) or ((now_ns - last_edit_ns) >= idle_ns)

            def marker_text(slide_index: int) -> str:
                return f"[Diapositiva {int(slide_index) + 1}]"

            def normalize(text: str) -> str:
                return (text or "").replace("\r\n", "\n").replace("\r", "\n")

            inserted_marker: Optional[str] = None

            if pending is None and has_been_idle and new_notes.strip() and not old.strip():
                pending = int(getattr(self, "current_slide_index", 0) or 0)

            if pending is not None and has_been_idle and new_notes.strip():
                marker = marker_text(pending)
                old_norm = normalize(old)
                new_norm = normalize(new_notes)
                old_trim = old_norm.rstrip()

                if not old_trim.strip():
                    payload = new_norm.lstrip()
                    self.student_notes = f"{marker}\n{payload}\n" if not payload.endswith("\n") else f"{marker}\n{payload}"
                    inserted_marker = marker
                    self._pending_marker_slide_index = None
                elif new_norm.startswith(old_trim) and len(new_norm) > len(old_trim):
                    appended = new_norm[len(old_trim):]
                    tail = old_trim.rstrip()
                    if not tail.endswith(marker):
                        sep = "\n\n" if tail else ""
                        self.student_notes = f"{tail}{sep}{marker}\n{appended.lstrip('\n')}"
                        inserted_marker = marker
                        self._pending_marker_slide_index = None
                    else:
                        self.student_notes = new_norm
                        self._pending_marker_slide_index = None
                else:
                    prefix_len = 0
                    max_prefix = min(len(old_trim), len(new_norm))
                    while prefix_len < max_prefix and old_trim[prefix_len] == new_norm[prefix_len]:
                        prefix_len += 1
                    near_end = prefix_len >= max(0, len(old_trim) - 3)
                    if near_end and len(new_norm) > prefix_len:
                        appended = new_norm[prefix_len:]
                        base = old_trim[:prefix_len].rstrip()
                        if not base.endswith(marker):
                            sep = "\n\n" if base else ""
                            self.student_notes = f"{base}{sep}{marker}\n{appended.lstrip('\n')}"
                            inserted_marker = marker
                            self._pending_marker_slide_index = None
                        else:
                            self.student_notes = new_norm
                            self._pending_marker_slide_index = None
                    else:
                        self.student_notes = new_norm
            else:
                self.student_notes = normalize(new_notes)

            self._last_notes_edit_ns = now_ns
            if self.student_notes.strip():
                self._notes_ever_written = True
            note_len = len(self.student_notes.strip())

        if note_len > 0:
            logger.debug("Notas actualizadas (len=%d).", note_len)
        if inserted_marker:
            logger.info("Auto-marca añadida: %s", inserted_marker)
            return self.student_notes
        return None

    def _start_notes_export(self, token_for_notes: str) -> None:
        token_for_notes = (token_for_notes or "latest").strip() or "latest"
        with self.lock:
            if self._notes_export_inflight_token == token_for_notes:
                return
            existing_token = self._notes_pdf_token
            existing_path = self.notes_pdf_path
            if existing_token == token_for_notes and existing_path and os.path.exists(existing_path):
                return
            self._notes_export_inflight_token = token_for_notes
            self.notes_pdf_status = f"PDF notas alumno: generando ({token_for_notes})..."

        t = threading.Thread(target=self._run_notes_export, args=(token_for_notes,), daemon=True)
        t.start()

    def _run_notes_export(self, token_for_notes: str) -> None:
        try:
            with self.lock:
                raw_notes = self.student_notes or ""

            if not raw_notes.strip():
                with self.lock:
                    self.notes_format_status = "Formateo notas: sin notas."
                notes_to_export = ""
            else:
                with self.lock:
                    self.notes_format_status = "Formateo notas: en curso..."
                    should_log_format = token_for_notes != self._log_format_token
                    if should_log_format:
                        self._log_format_token = token_for_notes
                if should_log_format:
                    logger.info("Formateando notas con LLM (token=%s)...", token_for_notes)

                formatted = self._format_notes_with_llm(raw_notes)
                with self.lock:
                    self._notes_formatted_token = token_for_notes
                    self._notes_formatted_text = formatted
                if should_log_format:
                    logger.info("Formateo de notas terminado (token=%s).", token_for_notes)

                notes_to_export = formatted or self._clean_notes_whitespace(raw_notes)

            notes_path = self._export_student_notes_pdf(token_for_notes, notes_to_export)
            with self.lock:
                self.notes_pdf_path = notes_path
                self._notes_pdf_token = token_for_notes
                self.notes_pdf_status = f"PDF notas alumno guardado: {notes_path}"
                should_log_notes = token_for_notes != self._log_notes_pdf_token
                if should_log_notes:
                    self._log_notes_pdf_token = token_for_notes
                self._notes_export_inflight_token = None
            if should_log_notes:
                logger.info("Notas del alumno guardadas: %s", notes_path)
        except Exception as ex:
            with self.lock:
                self.notes_pdf_status = f"PDF notas alumno error: {type(ex).__name__}: {ex}"
                self._notes_export_inflight_token = None
            logger.error("ERROR guardando PDF notas alumno: %s: %s", type(ex).__name__, ex)

    @staticmethod
    def _clean_notes_whitespace(notes: str) -> str:
        cleaned = (notes or "").replace("\r\n", "\n").replace("\r", "\n")
        cleaned = "\n".join([line.rstrip() for line in cleaned.split("\n")])
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
        return cleaned.strip()

    def _get_notes_formatter_llm(self):
        if settings.is_simulation:
            return None
        try:
            if settings.llm_provider == "gemini":
                from langchain_google_vertexai import ChatVertexAI
                kwargs: Dict[str, Any] = {
                    "model_name": settings.gemini_vision_model_name,
                    "temperature": 0.0,
                }
                if settings.gcp_project:
                    kwargs["project"] = settings.gcp_project
                if settings.gcp_location:
                    kwargs["location"] = settings.gcp_location
                return ChatVertexAI(**kwargs)
            else:
                from langchain_ollama import ChatOllama
                kwargs = {
                    "model": settings.vision_model_name,
                    "temperature": 0.0,
                    "base_url": settings.ollama_base_url,
                    "num_gpu": settings.ollama_num_gpu,
                }
                try:
                    kwargs["client_kwargs"] = {"timeout": settings.llm_request_timeout_seconds}
                    return ChatOllama(**kwargs)
                except TypeError:
                    kwargs.pop("client_kwargs", None)
                    return ChatOllama(**kwargs)
        except Exception as ex:
            with self.lock:
                self.notes_format_status = f"Formateo notas error: {type(ex).__name__}: {ex}"
            return None

    def _format_notes_with_llm(self, notes: str) -> str:
        cleaned = self._clean_notes_whitespace(notes)
        if not cleaned:
            return ""

        llm = self._get_notes_formatter_llm()
        if llm is None:
            with self.lock:
                if not str(self.notes_format_status).startswith("Formateo notas error:"):
                    self.notes_format_status = "Formateo notas: limpieza básica (sin LLM)."
            return cleaned

        prompt = (
            "Eres un asistente de accesibilidad. Tu tarea es FORMATEAR y CORREGIR las notas de un alumno "
            "para que sean fáciles de leer con lector de pantalla.\n\n"
            "Prioridad principal:\n"
            "- El texto final debe ser gramaticalmente correcto, natural y fácil de leer con lector de pantalla.\n"
            "- Si una frase es gramaticalmente incorrecta o poco natural, debes reorganizarla manteniendo exactamente el mismo significado.\n\n"
            "Reglas estrictas:\n"
            "- NO elimines información.\n"
            "- NO resumas contenido.\n"
            "- NO inventes contenido nuevo.\n"
            "- NO cambies números, fechas, nombres propios, siglas, URLs ni símbolos.\n"
            "- Cambiar el orden de las palabras dentro de una oración SÍ está permitido si mejora la gramática o la claridad.\n"
            "- Sustituir expresiones equivalentes (por ejemplo: 'tener que' → 'deber') SÍ está permitido.\n\n"
            "Solo puedes:\n"
            "  * Corregir ortografía y acentos.\n"
            "  * Eliminar repeticiones accidentales de letras (por ejemplo: 'essss' → 'es').\n"
            "  * Corregir abreviaciones informales si su significado es evidente (por ejemplo: 'q' → 'que', 'tnen' → 'tienen').\n"
            "  * Arreglar espacios incorrectos, guiones y saltos de línea.\n"
            "  * Unir frases partidas por saltos de línea en párrafos coherentes.\n"
            "  * Añadir puntuación mínima necesaria (comas o puntos) para mejorar la legibilidad.\n"
            "  * Reorganizar el orden de las palabras dentro de la oración si mejora la naturalidad.\n"
            "  * Reescribir frases con una estructura gramatical más correcta manteniendo el significado exacto.\n\n"
            "Importante:\n"
            "- Mantén siempre el mismo significado original.\n"
            "- Mantén el orden de las ideas del texto.\n"
            "- Si hay listas, consérvalas como listas.\n"
            "- No simplifiques el contenido académico.\n"
            "- No elimines repeticiones intencionales del alumno (solo errores evidentes).\n"
            "- Prioriza claridad gramatical sobre el orden literal original de las palabras.\n"
            "- Devuelve SOLO el texto final corregido, sin explicaciones.\n\n"
            "NOTAS (entrada):\n"
            "```text\n"
            f"{cleaned}\n"
            "```\n"
            "NOTAS (salida):"
        )
        try:
            msg = llm.invoke([HumanMessage(content=prompt)])
            output = self._clean_notes_whitespace(getattr(msg, "content", "") or "")
            with self.lock:
                self.notes_format_status = "Formateo notas: listo."
            return output or cleaned
        except Exception as ex:
            with self.lock:
                self.notes_format_status = f"Formateo notas error: {type(ex).__name__}: {ex}"
            return cleaned

    def _export_student_notes_pdf(self, token: str, notes_text: str) -> str:
        notes = (notes_text or "").strip()
        with self.lock:
            session_key = (self.session_key or "").strip() or "-"

        title_lines = [f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
        body_lines = ["(Sin notas)"] if not notes else notes.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        fontname = "helv"
        fontsize = 12
        line_height = int(fontsize * 1.35)
        margin = 50
        page_width, page_height = 595, 842
        max_width = page_width - (2 * margin)

        def wrap_line(line: str) -> List[str]:
            line = (line or "").strip()
            if not line:
                return [""]
            words = line.split()
            wrapped: List[str] = []
            current = ""
            for word in words:
                candidate = f"{current} {word}".strip() if current else word
                if fitz.get_text_length(candidate, fontname=fontname, fontsize=fontsize) <= max_width:
                    current = candidate
                    continue
                if current:
                    wrapped.append(current)
                    current = ""
                if fitz.get_text_length(word, fontname=fontname, fontsize=fontsize) <= max_width:
                    current = word
                    continue
                chunk = ""
                for ch in word:
                    candidate_chunk = f"{chunk}{ch}"
                    if chunk and fitz.get_text_length(candidate_chunk, fontname=fontname, fontsize=fontsize) > max_width:
                        wrapped.append(chunk)
                        chunk = ch
                    else:
                        chunk = candidate_chunk
                if chunk:
                    current = chunk
            if current:
                wrapped.append(current)
            return wrapped

        all_lines: List[str] = []
        for raw in title_lines:
            all_lines.extend(wrap_line(raw))
        for raw in body_lines:
            all_lines.extend(wrap_line(raw))

        doc = fitz.open()
        page = doc.new_page(width=page_width, height=page_height)
        y = margin + fontsize
        for line in all_lines:
            if y + line_height > (page_height - margin):
                page = doc.new_page(width=page_width, height=page_height)
                y = margin + fontsize
            if line:
                page.insert_text((margin, y), line, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
            y += line_height

        target_dir = self._download_dir()
        out_name = f"notas_alumno_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.pdf"
        out_path = os.path.join(target_dir, out_name)
        doc.save(out_path, deflate=True)
        doc.close()
        return out_path

    def _download_dir(self) -> str:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        return downloads if os.path.isdir(downloads) else self._cache_dir

    def _request_json(self, path: str) -> Dict[str, Any]:
        if not self.remote_url or not self.session_key:
            raise RuntimeError("Introduce una clave válida.")
        query = urllib.parse.urlencode({"key": self.session_key})
        url = f"{self.remote_url}{path}?{query}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("Respuesta JSON invalida del servidor.")
        return data

    def _download_pdf(self, token: str) -> str:
        if not self.remote_url or not self.session_key:
            raise RuntimeError("Conexion no configurada.")
        query = urllib.parse.urlencode({"key": self.session_key})
        url = f"{self.remote_url}/sync/pdf?{query}"
        out_path = os.path.join(self._cache_dir, f"deck_{token or 'latest'}.pdf")
        req = urllib.request.Request(url, headers={"Accept": "application/pdf"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
        with open(out_path, "wb") as f:
            f.write(content)
        return out_path

    def _download_final_pdf(self, token: Optional[str]) -> str:
        if not self.remote_url or not self.session_key:
            raise RuntimeError("Conexion no configurada.")
        params: Dict[str, str] = {"key": self.session_key}
        if token:
            params["token"] = token
        url = f"{self.remote_url}/sync/final_pdf?{urllib.parse.urlencode(params)}"
        out_path = os.path.join(self._download_dir(), f"clase_final_notas_{token or 'latest'}.pdf")
        req = urllib.request.Request(url, headers={"Accept": "application/pdf"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            content = resp.read()
        with open(out_path, "wb") as f:
            f.write(content)
        return out_path

    def sync(self, force_pdf: bool = False) -> Tuple[bool, str]:
        try:
            state = self._request_json("/sync/state")
            remote_slide_idx = int(state.get("slide_index", 0))
            remote_slide_count = int(state.get("slide_count", 0))
            remote_status = str(state.get("status", "Sesión activa."))
            precompute_status = str(state.get("precompute_status", "Preproceso: sin PDF."))
            pdf_available = bool(state.get("pdf_available", False))
            new_token = (state.get("pdf_token") or "").strip() or None
            class_finished = bool(state.get("class_finished", False))
            final_pdf_token = (state.get("final_pdf_token") or "").strip() or None
            teacher_seq = int(state.get("teacher_input_seq", 0))
            teacher_text = (state.get("teacher_input_text") or "").strip()
            clarif_seq = int(state.get("clarification_seq", 0))
            clarif_text = (state.get("clarification") or "").strip()

            px = state.get("pointer_x_norm")
            py = state.get("pointer_y_norm")
            pts = state.get("pointer_ts_ms")
            try:
                px = float(px) if px is not None else None
                py = float(py) if py is not None else None
                pts = int(pts) if pts is not None else None
            except Exception:
                px = py = pts = None
            if px is not None and not (0.0 <= px <= 1.0):
                px = None
            if py is not None and not (0.0 <= py <= 1.0):
                py = None

            slide_changed = False
            with self.lock:
                new_idx = max(0, remote_slide_idx)
                self.current_slide_index = new_idx
                self.current_slide_count = max(0, remote_slide_count)
                self.remote_status = remote_status
                self.precompute_status = precompute_status
                if px is not None and py is not None and pts is not None:
                    self.pointer_x_norm, self.pointer_y_norm, self.pointer_ts_ms = px, py, pts
                else:
                    self.pointer_x_norm = self.pointer_y_norm = self.pointer_ts_ms = None
                if self._last_slide_index_seen is None:
                    self._last_slide_index_seen = new_idx
                elif new_idx != self._last_slide_index_seen:
                    self._pending_marker_slide_index = new_idx
                    self._last_slide_index_seen = new_idx
                    slide_changed = True
                if teacher_seq > self._last_teacher_seq and teacher_text:
                    self._last_teacher_seq = teacher_seq
                    self._pending_teacher_text = teacher_text
                if clarif_seq > self._last_clarification_seq and clarif_text:
                    self._last_clarification_seq = clarif_seq
                    self._pending_clarification = clarif_text

            if slide_changed:
                logger.info("Cambio de diapositiva detectado: %d", new_idx + 1)

            should_download = pdf_available and (
                force_pdf
                or not self.local_pdf_path
                or not os.path.exists(self.local_pdf_path)
                or (new_token and new_token != self._pdf_token)
            )
            if should_download:
                local_path = self._download_pdf(new_token or "latest")
                with self.lock:
                    self.local_pdf_path = local_path
                    self._pdf_token = new_token
                    self._slide_cache.clear()
                if settings.precompute_on_upload and self.current_slide_count > 0:
                    slide_precompute_service.enqueue_pdf(local_path, self.current_slide_count, mode="all")

            now_ns = time.time_ns()
            with self.lock:
                final_path_existing = self.final_pdf_path
                last_attempt_ns = self._final_pdf_last_attempt_ns
                notes_path_existing = self.notes_pdf_path
                notes_last_attempt_ns = self._notes_pdf_last_attempt_ns
                notes_token_existing = self._notes_pdf_token

            needs_final = (
                class_finished
                and (final_pdf_token or self._final_pdf_token is None)
                and (final_pdf_token != self._final_pdf_token or not final_path_existing)
            )
            if needs_final and (now_ns - last_attempt_ns) > 5_000_000_000:
                with self.lock:
                    self._final_pdf_last_attempt_ns = now_ns
                try:
                    logger.info("Descargando PDF final (token=%s)...", final_pdf_token or "latest")
                    final_path = self._download_final_pdf(final_pdf_token)
                    with self.lock:
                        self.final_pdf_path = final_path
                        self._final_pdf_token = final_pdf_token or "latest"
                        self.final_pdf_status = f"PDF final descargado: {final_path}"
                        should_log = final_pdf_token != self._log_final_pdf_token
                        if should_log:
                            self._log_final_pdf_token = final_pdf_token
                    if should_log:
                        logger.info("Presentación modificada guardada: %s", final_path)
                except Exception as ex:
                    with self.lock:
                        self.final_pdf_status = f"PDF final error: {type(ex).__name__}: {ex}"
                    logger.error("ERROR descargando PDF final: %s: %s", type(ex).__name__, ex)

            token_for_notes = (final_pdf_token or self._final_pdf_token or "latest").strip() or "latest"
            needs_notes = class_finished and (token_for_notes != notes_token_existing or not notes_path_existing)
            if needs_notes and (now_ns - notes_last_attempt_ns) > 5_000_000_000:
                with self.lock:
                    self._notes_pdf_last_attempt_ns = now_ns
                try:
                    self._start_notes_export(token_for_notes)
                except Exception as ex:
                    with self.lock:
                        self.notes_pdf_status = f"PDF notas alumno error: {type(ex).__name__}: {ex}"
                    logger.error("ERROR lanzando exportación de notas: %s: %s", type(ex).__name__, ex)

            with self.lock:
                final_path_done = self.final_pdf_path
                notes_path_done = self.notes_pdf_path
                final_token_done = self._final_pdf_token
                notes_token_done = self._notes_pdf_token
                both_token = notes_token_done or final_token_done
                should_log_both = (
                    class_finished
                    and final_path_done
                    and notes_path_done
                    and (final_token_done == notes_token_done or not final_token_done or not notes_token_done)
                    and both_token != self._log_both_saved_token
                )
                if should_log_both:
                    self._log_both_saved_token = both_token
            if should_log_both:
                logger.info(
                    "Clase finalizada: guardados PDF final (%s) y notas (%s).",
                    final_path_done, notes_path_done,
                )

            if not pdf_available:
                with self.lock:
                    self.local_pdf_path = None
                    self._pdf_token = None
                    self._slide_cache.clear()
            else:
                with self.lock:
                    local_pdf_path = self.local_pdf_path
                    local_slide_count = self.current_slide_count
                if (
                    settings.precompute_on_upload
                    and local_pdf_path
                    and local_slide_count > 0
                    and os.path.exists(local_pdf_path)
                ):
                    done, total, failed, processing = slide_knowledge_store.get_deck_progress_by_pdf(local_pdf_path)
                    pending = max(0, total - done - failed - processing)
                    if pending > 0 and not slide_precompute_service.is_pdf_inflight(local_pdf_path):
                        slide_precompute_service.enqueue_pdf(local_pdf_path, local_slide_count, mode="all")

            with self.lock:
                self._last_sync_error = None
            return True, "Conexión exitosa."

        except Exception as ex:
            err = f"{type(ex).__name__}: {ex}"
            with self.lock:
                prev = self._last_sync_error
                if err != prev:
                    self._last_sync_error = err
                    should_log = True
                else:
                    should_log = False
            if should_log:
                logger.error("Sincronización error: %s", err)
            return False, err

    def consume_teacher_text(self) -> Optional[str]:
        with self.lock:
            text = self._pending_teacher_text
            self._pending_teacher_text = None
            return text

    def consume_clarification(self) -> Optional[str]:
        with self.lock:
            text = self._pending_clarification
            self._pending_clarification = None
            return text

    def render_current_slide(self) -> Optional[str]:
        with self.lock:
            pdf_path = self.local_pdf_path
            slide_count = self.current_slide_count
            slide_idx = self.current_slide_index
        if not pdf_path or not os.path.exists(pdf_path):
            return None
        try:
            return self._renderer.render(pdf_path, slide_idx, slide_count)
        except Exception:
            return None

    def snapshot(
        self,
    ) -> Tuple[str, Optional[str], str, str, Optional[str], int, int, Optional[float], Optional[float], Optional[int], str, str, str]:
        with self.lock:
            count = self.current_slide_count
            idx = self.current_slide_index
            remote_status = self.remote_status
            precompute_status = self.precompute_status
            pdf_path = self.local_pdf_path
            px = self.pointer_x_norm
            py = self.pointer_y_norm
            pts = self.pointer_ts_ms
            final_status = self.final_pdf_status
            notes_status = self.notes_pdf_status
            format_status = self.notes_format_status
        preview = self.render_current_slide()
        label = f"Diapositiva {idx + 1}/{count}" if count > 0 else "Sin PDF"
        local_precompute = slide_knowledge_store.deck_status_text(pdf_path)
        return (
            label, preview, remote_status, precompute_status,
            pdf_path, idx, count, px, py, pts,
            final_status, notes_status, format_status,
        )

    def debug_log_text(self, last_n: int = 40) -> str:
        _ = last_n
        return ""