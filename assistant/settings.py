import os
from typing import Any, Callable, Dict, Optional, Tuple
import yaml

_REQUIRED = object()

def _lower_str(value: Any) -> str:
    return str(value).strip().lower()

def _stripped_str(value: Any) -> str:
    return str(value).strip()

def _streaming_mode(value: Any) -> str:
    return str(value).strip() or "fixed"

_FIELDS: Dict[str, Tuple[str, str, Optional[Callable[[Any], Any]], Any]] = {
    "window_size": ("system", "window_size", int, _REQUIRED),
    "is_simulation": ("system", "simulation_mode", bool, _REQUIRED),
    "router_confidence_threshold": ("system", "router_confidence", float, _REQUIRED),
    "precompute_on_upload": ("system", "precompute_on_upload", bool, True),
    "use_precomputed_descriptions": ("system", "use_precomputed_descriptions", bool, True),
    "precompute_render_scale": ("system", "precompute_render_scale", float, 1.4),
    "precompute_slide_timeout_seconds": ("system", "precompute_slide_timeout_seconds", float, 120),
    "precompute_retry_attempts": ("system", "precompute_retry_attempts", int, 3),
    "precompute_retry_backoff_seconds": ("system", "precompute_retry_backoff_seconds", float, 2.0),
    "precompute_inter_slide_delay_seconds": ("system", "precompute_inter_slide_delay_seconds", float, 0.8),
    "precompute_cooldown_every_n_slides": ("system", "precompute_cooldown_every_n_slides", int, 3),
    "precompute_cooldown_seconds": ("system", "precompute_cooldown_seconds", float, 4.0),
    "precompute_min_seconds_between_vision_calls": (
        "system", "precompute_min_seconds_between_vision_calls", float, 1.5,
    ),
    "precompute_vision_work_budget_seconds": (
        "system", "precompute_vision_work_budget_seconds", float, 180.0,
    ),
    "precompute_budget_cooldown_seconds": ("system", "precompute_budget_cooldown_seconds", float, 12.0),
    "precompute_timeout_cooldown_seconds": ("system", "precompute_timeout_cooldown_seconds", float, 20.0),
    "slide_knowledge_version": ("system", "slide_knowledge_version", int, 1),
    "slide_description_format": ("system", "slide_description_format", _lower_str, "text"),
    "slide_html_model": ("system", "slide_html_model", _stripped_str, "gemini-2.5-flash"),
    "llm_provider": ("llm", "provider", _lower_str, "ollama"),
    "router_model_name": ("llm", "router_model", None, _REQUIRED),
    "vision_model_name": ("llm", "vision_model", None, _REQUIRED),
    "ollama_base_url": ("llm", "base_url", None, _REQUIRED),
    "llm_request_timeout_seconds": ("llm", "request_timeout_seconds", float, 90),
    "ollama_num_gpu": ("llm", "num_gpu", int, 99),
    "gemini_router_model_name": ("llm", "gemini_router_model", str, "gemini-2.5-flash"),
    "gemini_vision_model_name": ("llm", "gemini_vision_model", str, "gemini-2.5-flash"),
    "gcp_project": ("llm", "gcp_project", str, ""),
    "gcp_location": ("llm", "gcp_location", str, "us-central1"),
    "audio_chunk_duration": ("audio", "chunk_duration", int, _REQUIRED),
    "whisper_model_size": ("audio", "whisper_model", None, _REQUIRED),
    "chunk_overlap": ("audio", "chunk_overlap", int, 0),
    "audio_streaming_mode": ("audio", "streaming_mode", _streaming_mode, "fixed"),
    "vad_frame_ms": ("audio", "vad_frame_ms", int, 30),
    "vad_energy_threshold": ("audio", "vad_energy_threshold", float, 0.01),
    "vad_preroll_seconds": ("audio", "vad_preroll_seconds", float, 0.2),
    "vad_silence_seconds": ("audio", "vad_silence_seconds", float, 0.6),
    "vad_min_speech_seconds": ("audio", "vad_min_speech_seconds", float, 0.3),
    "vad_max_segment_seconds": ("audio", "vad_max_segment_seconds", float, 12.0),
    "whisper_device": ("audio", "whisper_device", None, "auto"),
    "whisper_fp16": ("audio", "whisper_fp16", bool, True),
    "whisper_beam_size": ("audio", "whisper_beam_size", int, 5),
    "whisper_best_of": ("audio", "whisper_best_of", int, 5),
    "whisper_no_speech_threshold": ("audio", "whisper_no_speech_threshold", float, 0.45),
    "whisper_condition_on_previous_text": ("audio", "whisper_condition_on_previous_text", bool, True),
    "student_remote_url": ("student", "remote_url", _stripped_str, ""),
}

class Settings:

    def __init__(self, config_path: str = "settings.yaml"):
        self.base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(self.base_path, config_path)
        with open(full_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def __getattr__(self, name: str) -> Any:
        try:
            section, key, cast, default = _FIELDS[name]
        except KeyError:
            raise AttributeError(f"Setting desconocido: {name!r}") from None
        section_data = self.config.get(section) or {}
        if default is _REQUIRED and key not in section_data:
            raise KeyError(f"Falta la clave obligatoria '{section}.{key}' en settings.yaml")
        value = section_data.get(key, default)
        return cast(value) if cast is not None else value


    @property
    def ACTIVE_SLIDE_PROMPT_PROFILE(self) -> str:
        system_profile = (self.config.get("system") or {}).get("ACTIVE_SLIDE_PROMPT_PROFILE")
        return self.config.get("ACTIVE_SLIDE_PROMPT_PROFILE", system_profile or "ESTADISTICA")

    @property
    def SLIDE_DESCRIPTION_PROMPT_TEMPLATES(self) -> dict:
        system_templates = (self.config.get("system") or {}).get("SLIDE_DESCRIPTION_PROMPT_TEMPLATES")
        return self.config.get("SLIDE_DESCRIPTION_PROMPT_TEMPLATES", system_templates) or {}

    @property
    def slide_knowledge_db_path(self) -> str:
        configured = (self.config.get("system") or {}).get(
            "slide_knowledge_db_path", "slide_knowledge.sqlite3"
        )
        if os.path.isabs(configured):
            return configured
        return os.path.abspath(os.path.join(self.base_path, configured))

settings = Settings()