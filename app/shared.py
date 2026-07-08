
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple
import fitz
from assistant.settings import settings
from assistant.slide_knowledge import slide_knowledge_store, slide_precompute_service
from assistant.slide_render import SlideRenderCache

logger = logging.getLogger(__name__)

class SharedPresentation:

    def __init__(self):
        self.lock = threading.Lock()
        self.session_key: Optional[str] = None
        self.pdf_path: Optional[str] = None
        self.slide_index = 0
        self.slide_count = 0
        self.status = "Sin presentación compartida."
        self.notes_pdf_path: Optional[str] = None
        self.notes_by_slide: Dict[int, List[str]] = {}
        self.class_finished = False
        self.final_pdf_path: Optional[str] = None
        self.final_pdf_token: Optional[str] = None
        self.pointer_x_norm: Optional[float] = None
        self.pointer_y_norm: Optional[float] = None
        self.pointer_ts_ms: Optional[int] = None
        self.pointer_slide_index: Optional[int] = None
        self.last_clarification: str = ""
        self.last_clarification_seq: int = 0
        self._renderer = SlideRenderCache("agenda2030_shared_slides")

    def _reset_notes(self, pdf_path: Optional[str]) -> None:
        self.notes_pdf_path = pdf_path
        self.notes_by_slide = {}
        self.class_finished = False
        self.final_pdf_path = None
        self.final_pdf_token = None
        self.pointer_x_norm = None
        self.pointer_y_norm = None
        self.pointer_ts_ms = None
        self.pointer_slide_index = None

    def update_pointer_from_payload(self, payload: str) -> None:
        raw = (payload or "").strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        try:
            x = float(data.get("x"))
            y = float(data.get("y"))
            ts = int(data.get("ts"))
        except Exception:
            return
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return
        with self.lock:
            self.pointer_x_norm = x
            self.pointer_y_norm = y
            self.pointer_ts_ms = ts
            self.pointer_slide_index = int(self.slide_index)

    def pointer_snapshot(self) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
        with self.lock:
            return self.pointer_x_norm, self.pointer_y_norm, self.pointer_ts_ms, self.pointer_slide_index

    def publish_clarification(self, text: str) -> None:
        clean = (text or "").strip()
        if not clean:
            return
        with self.lock:
            self.last_clarification_seq += 1
            self.last_clarification = clean

    def clarification_snapshot(self) -> Tuple[int, str]:
        with self.lock:
            return self.last_clarification_seq, self.last_clarification

    def set_session_key(self, key: str) -> str:
        clean_key = (key or "").strip()
        if not clean_key:
            return "La clave no puede estar vacia."
        with self.lock:
            self.session_key = clean_key
            self.pdf_path = None
            self.slide_index = 0
            self.slide_count = 0
            self.status = "Sesión creada por el profesor. Esperando PDF."
            self._reset_notes(None)
        return "Sesión de profesor iniciada."

    def validate_student_key(self, key: str) -> Tuple[bool, str]:
        clean_key = (key or "").strip()
        with self.lock:
            if not self.session_key:
                return False, "No hay sesión activa. El profesor debe crearla primero."
            if clean_key != self.session_key:
                return False, "Clave incorrecta."
            return True, "Acceso de alumno concedido."

    def set_pdf(self, pdf_path: Optional[str]) -> None:
        normalized = (pdf_path or "").strip() or None
        with self.lock:
            if normalized == self.pdf_path:
                return
            self.pdf_path = normalized
            self.slide_index = 0
            self.slide_count = 0
            self._reset_notes(normalized)

            if not normalized:
                self.status = "Presentación eliminada por el profesor."
                return
            try:
                with fitz.open(normalized) as doc:
                    self.slide_count = doc.page_count
                if settings.precompute_on_upload:
                    slide_precompute_service.enqueue_pdf(normalized, self.slide_count, mode="all")
                self.status = f"Presentación compartida ({self.slide_count} diapositivas)."
            except Exception as ex:
                self.pdf_path = None
                self.slide_count = 0
                self.status = f"No se pudo abrir el PDF compartido: {ex}"

    def add_note_for_slide(self, slide_index: int, note: str) -> None:
        clean = (note or "").strip()
        if not clean:
            return
        with self.lock:
            if not self.pdf_path:
                return
            if self.notes_pdf_path != self.pdf_path:
                self._reset_notes(self.pdf_path)
            self.notes_by_slide.setdefault(int(slide_index), []).append(clean)

    def _build_annotated_pdf(self, pdf_path: str, notes: Dict[int, List[str]]) -> str:
        if not notes:
            return pdf_path

        base = os.path.splitext(os.path.basename(pdf_path))[0]
        digest = hashlib.md5(f"{pdf_path}|{time.time_ns()}".encode("utf-8")).hexdigest()
        out_path = os.path.join(tempfile.gettempdir(), f"{base}_accesible_{digest}.pdf")

        with fitz.open(pdf_path) as doc:
            for slide_index in sorted(notes.keys(), reverse=True):
                slide_notes = notes[slide_index]
                original_page = doc.load_page(slide_index)
                rect = original_page.rect
                new_page = doc.new_page(pno=slide_index + 1, width=rect.width, height=rect.height)
                margin = 50
                text_rect = fitz.Rect(margin, margin, rect.width - margin, rect.height - margin)
                title = f"NOTAS DE ACCESIBILIDAD - DIAPOSITIVA {slide_index + 1}\n"
                content = "\n".join([f"• {text}" for text in slide_notes])
                full_text = title + "=" * 30 + "\n\n" + content
                new_page.insert_textbox(
                    text_rect, full_text, fontsize=12, fontname="helv", color=(0, 0, 0), align=0
                )
            doc.save(out_path, deflate=True)
        return out_path

    def finalize_class(self) -> Tuple[bool, str]:
        with self.lock:
            pdf_path = self.pdf_path
            notes = dict(self.notes_by_slide)
        if not pdf_path or not os.path.exists(pdf_path):
            return False, "No hay PDF compartido para finalizar la clase."
        try:
            final_path = self._build_annotated_pdf(pdf_path, notes)
        except Exception as ex:
            return False, f"No se pudo generar el PDF con notas: {ex}"
        with self.lock:
            self.class_finished = True
            self.final_pdf_path = final_path
            token_raw = f"{final_path}|{os.path.getsize(final_path)}|{int(os.path.getmtime(final_path))}"
            self.final_pdf_token = hashlib.md5(token_raw.encode("utf-8")).hexdigest()
            self.status = "Clase finalizada. PDF con notas listo."
        return True, "Clase finalizada. PDF con notas listo para descarga."

    def move_slide(self, delta: int) -> None:
        with self.lock:
            if self.slide_count <= 0:
                return
            self.slide_index = max(0, min(self.slide_index + int(delta), self.slide_count - 1))
            self.status = f"Profesor en diapositiva {self.slide_index + 1}/{self.slide_count}."
            self.pointer_x_norm = None
            self.pointer_y_norm = None
            self.pointer_ts_ms = None
            self.pointer_slide_index = None

    def _render_current_slide(self) -> Optional[str]:
        try:
            return self._renderer.render(self.pdf_path, self.slide_index, self.slide_count)
        except Exception as ex:
            self.status = f"Error renderizando diapositiva compartida: {ex}"
            return None

    def snapshot(self) -> Tuple[str, Optional[str], str]:
        with self.lock:
            preview = self._render_current_slide()
            label = f"Diapositiva {self.slide_index + 1}/{self.slide_count}" if self.slide_count > 0 else "Sin PDF"
            session_text = "Sesión activa" if self.session_key else "Sin sesión"
            precompute = slide_knowledge_store.deck_status_text(self.pdf_path)
            return label, preview, f"{session_text} | {self.status} | {precompute}"

    def graph_pdf_context(self) -> Tuple[Optional[str], int, int, Optional[str]]:
        with self.lock:
            preview = self._render_current_slide()
            return self.pdf_path, self.slide_index, self.slide_count, preview


class SharedTeacherInput:

    def __init__(self):
        self.lock = threading.Lock()
        self.seq = 0
        self.text = ""

    def publish(self, text: str) -> None:
        clean = (text or "").strip()
        if not clean:
            return
        with self.lock:
            self.seq += 1
            self.text = clean

    def snapshot(self) -> Tuple[int, str]:
        with self.lock:
            return self.seq, self.text


shared_presentation = SharedPresentation()
shared_teacher_input = SharedTeacherInput()