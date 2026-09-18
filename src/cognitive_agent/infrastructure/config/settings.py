from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from ...application.settings import (
    AccessibilitySettings,
    ApplicationSettings,
    ClarificationSettings,
    DeixisSettings,
    NotesSettings,
    SessionSettings,
)
from ...domain.value_objects.subject import Subject

ENV_PREFIX = "COGNITIVE_AGENT__"
ENV_NAME_VAR = "COGNITIVE_AGENT_ENV"

@dataclass(slots=True)
class LlmConfig:
    provider: str = "gemini"
    detection_provider: str | None = None
    clarification_provider: str | None = None
    notes_provider: str | None = None
    deixis_provider: str | None = None
    clarification_model: str = "gemini-2.5-flash"
    deixis_model: str = "gemini-2.5-flash"
    detection_model: str = "gemini-3.6-flash"
    description_model: str = "gemini-2.5-flash"
    notes_model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    request_timeout_seconds: float = 90.0
    gcp_project: str = ""
    gcp_location: str = "us-central1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_router_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_vision_model: str = "qwen3-vl:8b-instruct"
    ollama_num_gpu: int = 99

@dataclass(slots=True)
class SttConfig:
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    language: str = "es"
    whisper_model: str = "small"
    whisper_device: str = "cpu"

@dataclass(slots=True)
class AudioConfig:

    vad_energy_threshold: float = 0.01
    vad_preroll_seconds: float = 0.2
    vad_silence_seconds: float = 0.6
    vad_min_speech_seconds: float = 0.3
    vad_max_segment_seconds: float = 12.0
    vad_calibration_seconds: float = 0.8
    vad_threshold_factor: float = 2.5

@dataclass(slots=True)
class TtsConfig:
    provider: str = "browser"
    rate: int = 175

@dataclass(slots=True)
class PersistenceConfig:
    backend: str = "file"
    data_dir: str = ".data"
    slide_knowledge_db: str = "slide_knowledge.sqlite3"

@dataclass(slots=True)
class PromptsConfig:
    directory: str = "prompts"
    registry: str = "prompts/registry.yaml"

@dataclass(slots=True)
class TelemetryConfig:
    enabled: bool = True
    redact_content: bool = True
    sink: str = "logging"
    file_path: str = "telemetry.jsonl"

@dataclass(slots=True)
class SchedulerConfig:
    workers: int = 2
    queue_size: int = 32

@dataclass(slots=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 7860
    student_ui_port: int = 7861
    teacher_base_url: str = "http://127.0.0.1:7860"

@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = "text"

@dataclass(slots=True)
class Settings:
    environment: str = "development"
    session: SessionSettings = field(default_factory=SessionSettings)
    notes: NotesSettings = field(default_factory=NotesSettings)
    clarification: ClarificationSettings = field(default_factory=ClarificationSettings)
    deixis: DeixisSettings = field(default_factory=DeixisSettings)
    accessibility: AccessibilitySettings = field(default_factory=AccessibilitySettings)
    llm: LlmConfig = field(default_factory=LlmConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    root: Path = field(default_factory=Path.cwd)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def data_dir(self) -> Path:
        path = Path(self.persistence.data_dir)
        return path if path.is_absolute() else self.root / path

    @property
    def prompts_dir(self) -> Path:
        path = Path(self.prompts.directory)
        return path if path.is_absolute() else self.root / path

    @property
    def prompts_registry(self) -> Path:
        path = Path(self.prompts.registry)
        return path if path.is_absolute() else self.root / path

    @property
    def slide_knowledge_db(self) -> Path:
        path = Path(self.persistence.slide_knowledge_db)
        return path if path.is_absolute() else self.root / path

    @property
    def telemetry_file(self) -> Path:
        path = Path(self.telemetry.file_path)
        return path if path.is_absolute() else self.data_dir / path

    @property
    def deixis_classifier_model(self) -> Path:
        path = Path(self.deixis.classifier_model_path)
        return path if path.is_absolute() else self.root / path

    def application(self) -> ApplicationSettings:

        return ApplicationSettings(
            session=self.session,
            notes=self.notes,
            clarification=self.clarification,
            deixis=self.deixis,
            accessibility=self.accessibility,
        )

    def validate(self) -> list[str]:

        problems: list[str] = []
        if self.notes.slide_tag_idle_seconds < 0:
            problems.append("notes.slide_tag_idle_seconds no puede ser negativo.")
        if self.clarification.timeout_seconds <= 0:
            problems.append("clarification.timeout_seconds debe ser mayor que cero.")
        if self.clarification.max_words < 5:
            problems.append("clarification.max_words es demasiado bajo para ser util.")
        if self.session.transcript_window < 1:
            problems.append("session.transcript_window debe ser al menos 1.")
        if self.session.context_max_previous_fragments < 1:
            problems.append("session.context_max_previous_fragments debe ser al menos 1.")
        if self.session.context_max_previous_fragments >= self.session.transcript_window:
            problems.append(
                "session.context_max_previous_fragments debe ser menor que transcript_window."
            )
        if self.session.context_max_age_seconds <= 0:
            problems.append("session.context_max_age_seconds debe ser mayor que cero.")
        if self.session.context_max_chars < 1:
            problems.append("session.context_max_chars debe ser al menos 1.")
        if not 0 <= self.session.context_keep_after_clarification <= self.session.transcript_window:
            problems.append(
                "session.context_keep_after_clarification debe estar entre 0 y transcript_window."
            )
        if self.llm.provider not in {"gemini", "ollama", "fake"}:
            problems.append(f"llm.provider desconocido: {self.llm.provider}")
        if self.llm.detection_provider not in {None, "", "gemini", "ollama", "fake"}:
            problems.append(f"llm.detection_provider desconocido: {self.llm.detection_provider}")
        if self.llm.clarification_provider not in {None, "", "gemini", "ollama", "fake"}:
            problems.append(
                f"llm.clarification_provider desconocido: {self.llm.clarification_provider}"
            )
        if self.llm.notes_provider not in {None, "", "gemini", "ollama", "fake"}:
            problems.append(f"llm.notes_provider desconocido: {self.llm.notes_provider}")
        if self.llm.deixis_provider not in {None, "", "gemini", "ollama", "fake"}:
            problems.append(f"llm.deixis_provider desconocido: {self.llm.deixis_provider}")
        if self.stt.provider not in {"gemini", "whisper_local", "fake"}:
            problems.append(f"stt.provider desconocido: {self.stt.provider}")
        if self.tts.provider not in {"browser", "pyttsx3", "null"}:
            problems.append(f"tts.provider desconocido: {self.tts.provider}")
        if self.persistence.backend not in {"memory", "file"}:
            problems.append(f"persistence.backend desconocido: {self.persistence.backend}")
        if self.telemetry.sink not in {"logging", "jsonl", "both", "null"}:
            problems.append(f"telemetry.sink desconocido: {self.telemetry.sink}")
        if self.deixis.detector not in {
            "rules",
            "llm",
            "rules_then_llm",
            "rules_then_classifier",
        }:
            problems.append(f"deixis.detector desconocido: {self.deixis.detector}")
        if not (
            self.deixis.classifier_threshold < 0
            or 0.0 <= self.deixis.classifier_threshold <= 1.0
        ):
            problems.append("deixis.classifier_threshold debe estar entre 0 y 1, o ser negativo.")
        if (
            self.deixis.detector == "rules_then_classifier"
            and not self.deixis_classifier_model.is_file()
        ):
            problems.append(
                f"No se encuentra el clasificador de deixis: {self.deixis_classifier_model}"
            )
        if self.clarification.on_stale_slide not in {"keep", "discard"}:
            problems.append(
                f"clarification.on_stale_slide desconocido: {self.clarification.on_stale_slide}"
            )
        if not self.prompts_registry.is_file():
            problems.append(f"No se encuentra el registro de prompts: {self.prompts_registry}")
        return problems

def _deep_merge(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged

def _coerce(value: Any, target_type: Any) -> Any:
    if target_type is bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is str:
        return str(value)
    if target_type is Subject or target_type == "Subject":
        return Subject.parse(value)
    return value

def _apply(instance: Any, data: dict) -> Any:

    if not is_dataclass(instance) or not isinstance(data, dict):
        return instance

    for f in fields(instance):
        if f.name not in data:
            continue
        raw = data[f.name]
        current = getattr(instance, f.name)
        if is_dataclass(current) and isinstance(raw, dict):
            _apply(current, raw)
            continue
        if isinstance(current, dict) and isinstance(raw, dict):
            merged = {**current, **raw}
            object.__setattr__(instance, f.name, merged)
            continue
        try:
            if f.name == "default_subject":
                coerced = Subject.parse(raw)
            else:
                coerced = _coerce(raw, type(current)) if current is not None else raw
        except (TypeError, ValueError):
            coerced = raw
        object.__setattr__(instance, f.name, coerced)
    return instance

def _env_overlay() -> dict:

    overlay: dict = {}
    for raw_key, raw_value in os.environ.items():
        if not raw_key.startswith(ENV_PREFIX):
            continue
        path = [part.lower() for part in raw_key[len(ENV_PREFIX) :].split("__") if part]
        if not path:
            continue
        try:
            value: Any = json.loads(raw_value)
        except (TypeError, ValueError):
            value = raw_value
        cursor = overlay
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path[-1]] = value
    return overlay

def _cloud_run_overlay() -> dict:

    port = os.getenv("PORT")
    if not port:
        return {}
    try:
        return {"server": {"host": "0.0.0.0", "port": int(port)}}
    except ValueError:
        return {}

def find_project_root(start: Path | None = None) -> Path:

    current = (start or Path(__file__).resolve()).resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() or (
            (candidate / "config").is_dir() and (candidate / "prompts").is_dir()
        ):
            return candidate
    return Path.cwd()

def load_settings(
    *,
    environment: str | None = None,
    config_dir: Path | str | None = None,
    root: Path | str | None = None,
    overrides: dict | None = None,
) -> Settings:
    project_root = Path(root) if root else find_project_root()
    directory = Path(config_dir) if config_dir else project_root / "config"
    env_name = environment or os.getenv(ENV_NAME_VAR, "development")

    data: dict = {}
    default_file = directory / "default.yaml"
    if default_file.is_file():
        data = yaml.safe_load(default_file.read_text(encoding="utf-8")) or {}

    env_file = directory / f"{env_name}.yaml"
    if env_file.is_file():
        data = _deep_merge(data, yaml.safe_load(env_file.read_text(encoding="utf-8")) or {})

    data = _deep_merge(data, _env_overlay())
    data = _deep_merge(data, _cloud_run_overlay())
    if overrides:
        data = _deep_merge(data, overrides)

    settings = Settings(root=project_root)
    _apply(settings, data)
    settings.environment = str(data.get("environment", env_name))
    return settings
