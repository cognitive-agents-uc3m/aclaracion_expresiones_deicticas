import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from assistant.assistant import app as agent_app
from assistant.settings import settings
from assistant.state import format_router_info, new_agent_state
from assistant.tools import hardware
from .sync import RemoteDeckSync

logger = logging.getLogger(__name__)

class LocalSessionRuntime:

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.current_state = new_agent_state()
        self.latest_router = "Sin análisis"
        self.latest_status = "Sesión local lista."
        self.last_spoken_text = ""
        self.last_deictic_clarification = ""

    def __getstate__(self) -> dict:
        state = dict(self.__dict__)
        state["lock"] = None
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state or {})
        self.lock = threading.Lock()
        if "last_deictic_clarification" not in self.__dict__:
            self.last_deictic_clarification = ""

    def _format_router(self, state: Dict[str, Any]) -> str:
        return format_router_info(state)

    def process_input(self, text: str, audio_input: Any, sync: RemoteDeckSync) -> None:
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
                self.latest_status = "No se detecto texto ni voz legible."
            return

        _, preview, _, _, pdf_path, slide_idx, slide_count, px, py, pts, _, _, _ = sync.snapshot()

        with self.lock:
            persistent_buffer = list(self.current_state.get("transcript_buffer", []))

        buffer = list(persistent_buffer)
        buffer.append(text_detected.strip())
        if len(buffer) > settings.window_size:
            buffer = buffer[-settings.window_size:]

        inputs = {
            **new_agent_state(),
            "transcript_buffer": buffer,
            "uploaded_image": preview,
            "uploaded_pdf": pdf_path,
            "current_slide_index": slide_idx,
            "current_slide_count": slide_count,
            "current_context_text": " ".join(buffer),
            "pointer_x_norm": px,
            "pointer_y_norm": py,
            "pointer_ts_ms": pts,
        }

        output = agent_app.invoke(inputs)
        trigger_visual = bool(output.get("router_tool_called", False))
        committed_buffer = persistent_buffer[-settings.window_size:] if trigger_visual else buffer
        output["transcript_buffer"] = committed_buffer
        output["current_context_text"] = " ".join(committed_buffer)

        with self.lock:
            self.current_state = output
            self.latest_router = self._format_router(output)
            self.latest_status = "Inferencia local completada."
            deictic = (output.get("deictic_expression") or "").strip()
            desc = (output.get("generated_description") or "").strip()
            if deictic and desc and trigger_visual:
                self.last_deictic_clarification = desc

    def speak_description(self) -> str:
        with self.lock:
            text = (self.current_state.get("generated_description") or "").strip()
        if not text:
            return "No hay descripcion disponible."
        hardware.speak_text(text)
        with self.lock:
            self.last_spoken_text = text
        return text

    def snapshot(self) -> Tuple[str, str, str, bool]:
        with self.lock:
            desc = (self.current_state.get("generated_description") or "").strip()
            spoken = (self.last_spoken_text or "").strip()
            visual = bool(self.current_state.get("router_tool_called", False))
            shown_text = desc if desc else spoken
            return self.latest_router, self.latest_status, shown_text, visual

def ensure_sync(sync_obj: Optional[RemoteDeckSync]) -> RemoteDeckSync:
    return sync_obj if isinstance(sync_obj, RemoteDeckSync) else RemoteDeckSync()

def ensure_runtime(rt_obj: Optional[LocalSessionRuntime]) -> LocalSessionRuntime:
    return rt_obj if isinstance(rt_obj, LocalSessionRuntime) else LocalSessionRuntime()

def auto_session_key(now: Optional[datetime] = None) -> str:
    _ = now
    return "comodin"