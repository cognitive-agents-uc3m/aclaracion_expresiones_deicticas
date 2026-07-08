import logging
import queue
import threading
import time
from typing import Any, Dict, Optional, Tuple
import numpy as np
from assistant.assistant import app as agent_app
from assistant.settings import settings
from assistant.slide_render import SlideRenderCache
from assistant.state import format_router_info, new_agent_state
from assistant.tools import hardware
from .shared import shared_presentation

logger = logging.getLogger(__name__)

class SessionRuntime:

    def __init__(self):
        self.lock = threading.Lock()
        self.current_state = new_agent_state()
        self.latest_router_info = "Sin análisis"
        self.latest_status = "Sesión lista."
        self.latest_visual = False
        self.auto_mode = False
        self.last_transcribed_chunk = ""
        self.last_chunk_text = ""
        self.last_spoken_description = ""
        self._pending_tts_payload: Optional[str] = None
        self._last_clicked_element_ts_ms: Optional[int] = None
        self._last_clicked_element_text: str = ""
        self.current_pdf_path: Optional[str] = None
        self.current_slide_index = 0
        self.current_slide_count = 0
        self._renderer = SlideRenderCache("agenda2030_slides")

        self._audio_queue: "queue.Queue[Tuple[int, np.ndarray, Optional[str]]]" = queue.Queue(maxsize=12)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _format_router(self, state: Dict[str, Any]) -> Tuple[str, bool]:
        return format_router_info(state), bool(state.get("router_tool_called", False))

    def _set_pdf_if_needed(self, pdf_path: Optional[str]) -> None:
        normalized = (pdf_path or "").strip() or None
        if normalized == self.current_pdf_path:
            return
        self.current_pdf_path = normalized
        self.current_slide_index = 0
        self.current_slide_count = 0
        if not normalized:
            self.latest_status = "PDF eliminado."
            return
        try:
            import fitz
            with fitz.open(normalized) as doc:
                self.current_slide_count = doc.page_count
            self.latest_status = f"PDF cargado ({self.current_slide_count} diapositivas)."
        except Exception as ex:
            self.current_pdf_path = None
            self.current_slide_count = 0
            self.latest_status = f"No se pudo cargar el PDF: {ex}"

    def _render_current_pdf_slide(self) -> Optional[str]:
        try:
            return self._renderer.render(
                self.current_pdf_path, self.current_slide_index, self.current_slide_count
            )
        except Exception as ex:
            self.latest_status = f"Error renderizando PDF: {ex}"
            return None

    def move_slide(self, delta: int, pdf_path: Optional[str]) -> None:
        with self.lock:
            self._set_pdf_if_needed(pdf_path)
            if self.current_slide_count <= 0:
                return
            self.current_slide_index = max(
                0, min(self.current_slide_index + int(delta), self.current_slide_count - 1)
            )
            self.latest_status = f"Diapositiva actual: {self.current_slide_index + 1}/{self.current_slide_count}."

    def slide_status(self) -> Tuple[str, Optional[str]]:
        with self.lock:
            preview = self._render_current_pdf_slide()
            label = (
                f"Diapositiva {self.current_slide_index + 1}/{self.current_slide_count}"
                if self.current_slide_count > 0 else "Sin PDF"
            )
            return label, preview

    def _resolve_visual_input(self, image_path: Optional[str], pdf_path: Optional[str]) -> Optional[str]:
        _, _, slide_count, slide_preview = shared_presentation.graph_pdf_context()
        if slide_count > 0 and slide_preview:
            return slide_preview
        return image_path

    def _invoke_graph(self, text: str, image_path: Optional[str]) -> None:
        with self.lock:
            persistent_buffer = list(self.current_state.get("transcript_buffer", []))
        current_pdf_path, current_slide_index, current_slide_count, _ = shared_presentation.graph_pdf_context()
        px, py, pts, pslide = shared_presentation.pointer_snapshot()
        if pslide is None or int(pslide) != int(current_slide_index):
            px = py = pts = None

        buffer = list(persistent_buffer)
        if text:
            buffer.append(text.strip())
            if len(buffer) > settings.window_size:
                buffer = buffer[-settings.window_size:]

        if not buffer:
            return

        inputs = {
            **new_agent_state(),
            "transcript_buffer": buffer,
            "uploaded_image": image_path,
            "uploaded_pdf": current_pdf_path,
            "current_slide_index": current_slide_index,
            "current_slide_count": current_slide_count,
            "current_context_text": " ".join(buffer),
            "pointer_x_norm": px,
            "pointer_y_norm": py,
            "pointer_ts_ms": pts,
        }

        output = agent_app.invoke(inputs)
        info_router, es_visual = self._format_router(output)
        trigger_visual = bool(output.get("router_tool_called", False))
        deictic = (output.get("deictic_expression") or "").strip()
        generated = (output.get("generated_description") or "").strip()
        if trigger_visual and deictic and generated and current_slide_count > 0:
            shared_presentation.add_note_for_slide(
                current_slide_index, f"Referencia '{deictic}': {generated}"
            )

        committed_buffer = persistent_buffer[-settings.window_size:] if trigger_visual else buffer
        output["transcript_buffer"] = committed_buffer
        output["current_context_text"] = " ".join(committed_buffer)

        description = (output.get("generated_description") or "").strip()
        if trigger_visual and description:
            shared_presentation.publish_clarification(description)
        should_auto_speak = bool(trigger_visual and description and description != self.last_spoken_description)
        if should_auto_speak:
            self._queue_client_tts(description)
            self.last_spoken_description = description

        with self.lock:
            self.current_state = output
            self.latest_router_info = info_router
            self.latest_visual = es_visual
            precomputed_used = bool(output.get("precomputed_used", False))
            if trigger_visual:
                source = "precomputada" if precomputed_used else "en vivo"
                tts_note = " Descripción enviada al navegador (TTS cliente)." if should_auto_speak else ""
                self.latest_status = (
                    f"Flujo actualizado. Último chunk no persistido (trigger visual). "
                    f"Respuesta {source}.{tts_note}"
                )
            else:
                self.latest_status = "Flujo actualizado."

    def process_manual_input(
        self, text: str, image_path: Optional[str], pdf_path: Optional[str], audio_input: Any
    ) -> Optional[str]:
        text_detected = (text or "").strip()

        if not text_detected and audio_input is not None:
            with self.lock:
                context_hint = self.current_state.get("current_context_text", "")
            if isinstance(audio_input, tuple) and len(audio_input) == 2:
                text_detected = hardware.transcribe_audio_array(
                    audio_input[0], audio_input[1], prompt_text=context_hint
                )
            elif isinstance(audio_input, str):
                text_detected = hardware.transcribe_audio_file(audio_input, prompt_text=context_hint)

        if not text_detected:
            with self.lock:
                self.latest_status = "No se detectó texto ni voz legible."
            return None

        visual_input = self._resolve_visual_input(image_path, pdf_path)
        self._invoke_graph(text_detected, visual_input)
        return text_detected

    def enqueue_audio_segment(self, sample_rate: int, samples: np.ndarray) -> Tuple[bool, str]:
        if sample_rate <= 0 or samples is None or getattr(samples, "size", 0) == 0:
            return False, "Segmento de audio vacío."
        if not self.auto_mode:
            return False, "Modo auto desactivado."
        visual_input = self._resolve_visual_input(None, None)
        try:
            self._audio_queue.put_nowait((int(sample_rate), samples, visual_input))
        except queue.Full:
            with self.lock:
                self.latest_status = "Cola de audio llena. Se descarta un segmento."
            return False, "Cola de audio llena. Se descarta un segmento."
        with self.lock:
            self.latest_status = "Segmento de voz encolado para transcripcion."
        return True, "Segmento encolado."

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                sample_rate, frame, image_path = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                with self.lock:
                    context_hint = self.current_state.get("current_context_text", "")
                text = hardware.transcribe_audio_array(sample_rate, frame, prompt_text=context_hint)
                normalized = text.strip().lower()
                with self.lock:
                    self.last_transcribed_chunk = (text or "").strip()
                    if normalized and normalized == self.last_chunk_text:
                        self.latest_status = "Chunk duplicado por solape; ignorado."
                        continue
                    if normalized:
                        self.last_chunk_text = normalized

                clean_text = (text or "").strip()
                if clean_text:
                    logger.info("[STT] %s", clean_text)
                if not text.strip():
                    with self.lock:
                        self.latest_status = "Chunk procesado sin voz legible."
                    continue
                self._invoke_graph(text, image_path)
            except Exception as ex:
                with self.lock:
                    self.latest_status = f"Error en worker: {ex}"
            finally:
                self._audio_queue.task_done()

    def set_auto_mode(self, enabled: bool) -> None:
        with self.lock:
            self.auto_mode = enabled
            if enabled:
                self.latest_status = "Auto streaming activo (VAD en el navegador)."
            else:
                self.last_chunk_text = ""
                self.latest_status = "Auto streaming detenido."

    def snapshot(self) -> Tuple[str, bool, str]:
        with self.lock:
            return self.latest_router_info, self.latest_visual, self.latest_status

    def _queue_client_tts(self, text: str) -> None:
        clean = (text or "").strip()
        if not clean:
            return
        self._pending_tts_payload = f"{time.time_ns()}|{clean}"

    def consume_tts_payload(self) -> Optional[str]:
        with self.lock:
            payload = self._pending_tts_payload
            self._pending_tts_payload = None
            return payload

    def speak_current_description(self) -> str:
        with self.lock:
            desc = self.current_state.get("generated_description")
        description = desc or "No hay descripción disponible."
        with self.lock:
            self._queue_client_tts(description)
        return description