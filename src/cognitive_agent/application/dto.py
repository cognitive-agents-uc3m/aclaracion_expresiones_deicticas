from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..domain.entities.clarification import ClarificationStatus
from ..domain.value_objects.identifiers import ClarificationId, SessionId, SlideIdentifier
from ..domain.value_objects.subject import Subject

@dataclass(frozen=True, slots=True)
class AudioChunk:

    data: bytes
    mime_type: str = "audio/wav"
    sample_rate: int | None = None
    channels: int = 1

    @property
    def is_empty(self) -> bool:
        return not self.data

@dataclass(frozen=True, slots=True)
class StartSessionCommand:
    subject: Subject = Subject.GENERIC
    title: str = ""
    access_key: str = ""
    session_id: SessionId | None = None

@dataclass(frozen=True, slots=True)
class RenameSessionCommand:
    session_id: SessionId
    title: str = ""

@dataclass(frozen=True, slots=True)
class LoadDeckCommand:
    session_id: SessionId
    deck_id: str
    slide_count: int
    title: str = ""
    source_name: str = ""

@dataclass(frozen=True, slots=True)
class ChangeSlideCommand:
    session_id: SessionId
    index: int | None = None
    delta: int | None = None

@dataclass(frozen=True, slots=True)
class TranscriptFragmentCommand:
    session_id: SessionId
    text: str = ""
    audio: AudioChunk | None = None
    received_at: datetime | None = None

    @property
    def has_payload(self) -> bool:
        return bool(self.text.strip()) or (self.audio is not None and not self.audio.is_empty)

@dataclass(frozen=True, slots=True)
class UpdateNotesCommand:
    session_id: SessionId
    text: str
    is_keystroke: bool = True

@dataclass(frozen=True, slots=True)
class InsertClarificationCommand:
    session_id: SessionId
    clarification_id: ClarificationId | None = None

    requested_by_student: bool = True

@dataclass(frozen=True, slots=True)
class ExportNotesCommand:
    session_id: SessionId
    fmt: str = "markdown"
    processed: bool = False

@dataclass(frozen=True, slots=True)
class SlideView:
    index: int
    number: int
    count: int
    label: str
    has_description: bool = False
    description: str = ""
    description_format: str = "text"
    description_ready: bool = False

    @property
    def is_empty(self) -> bool:
        return self.count == 0

@dataclass(frozen=True, slots=True)
class ClarificationView:
    clarification_id: str
    text: str
    slide_number: int
    slide_index: int
    status: str = ClarificationStatus.PENDING.value
    created_at: datetime | None = None
    is_stale: bool = False
    listened: bool = False
    inserted: bool = False
    model: str = ""
    prompt_version: str = ""
    latency_ms: int | None = None
    trigger_expression: str = ""
    trigger_fragment: str = ""

    @property
    def is_available(self) -> bool:
        return self.status == ClarificationStatus.READY.value and bool(self.text)

    @property
    def announcement(self) -> str:

        if not self.is_available:
            return ""
        if self.is_stale:
            return (
                f"Aclaracion disponible de la diapositiva {self.slide_number}. "
                "El profesor ya ha avanzado."
            )
        return f"Aclaracion disponible de la diapositiva {self.slide_number}."

@dataclass(frozen=True, slots=True)
class NotesView:
    text: str
    entry_count: int = 0
    current_slide_number: int | None = None
    outline: tuple[tuple[int, str, str], ...] = field(default_factory=tuple)
    caret_offset: int | None = None
    restored_markers: tuple[str, ...] = field(default_factory=tuple)
    inserted_markers: tuple[str, ...] = field(default_factory=tuple)
    announcement: str = ""

@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: str
    subject: str
    title: str
    is_active: bool
    slide: SlideView
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latest_clarification: ClarificationView | None = None
    student_count: int = 0

@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    provider: str = ""
    model: str = ""
    latency_ms: int | None = None
    language: str = "es"

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

@dataclass(frozen=True, slots=True)
class GeneratedClarification:

    text: str
    model: str = ""
    prompt_version: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

@dataclass(frozen=True, slots=True)
class SpeechOutput:

    text: str
    audio: bytes = b""
    mime_type: str = ""
    provider: str = "browser"

    @property
    def is_client_side(self) -> bool:
        return not self.audio

@dataclass(frozen=True, slots=True)
class ExportedNotes:
    content: bytes
    filename: str
    mime_type: str
    processed: bool = False
    disclaimer: str = ""

@dataclass(frozen=True, slots=True)
class ProcessFragmentResult:

    accepted: bool
    text: str = ""
    detected: bool = False
    expression: str = ""
    clarification_id: str | None = None
    reason: str = ""
    slide_number: int | None = None
