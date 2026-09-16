from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .entities.clarification import ClarificationStatus
from .value_objects.deictic import DeicticExpression
from .value_objects.identifiers import ClarificationId, NoteEntryId, SessionId, SlideIdentifier
from .value_objects.subject import Subject

@dataclass(frozen=True, slots=True)
class DomainEvent:
    occurred_at: datetime
    session_id: SessionId

    @property
    def name(self) -> str:
        return type(self).__name__

@dataclass(frozen=True, slots=True)
class SessionStarted(DomainEvent):
    subject: Subject = Subject.GENERIC
    title: str = ""

@dataclass(frozen=True, slots=True)
class SessionEnded(DomainEvent):
    duration_seconds: float = 0.0

@dataclass(frozen=True, slots=True)
class DeckLoaded(DomainEvent):
    slide_count: int = 0
    deck_title: str = ""

@dataclass(frozen=True, slots=True)
class SlideChanged(DomainEvent):

    slide: SlideIdentifier | None = None
    previous: SlideIdentifier | None = None
    slide_count: int = 0

@dataclass(frozen=True, slots=True)
class TranscriptFragmentReceived(DomainEvent):
    text: str = ""
    slide: SlideIdentifier | None = None
    latency_ms: int | None = None

@dataclass(frozen=True, slots=True)
class DeicticExpressionDetected(DomainEvent):
    expression: DeicticExpression | None = None
    slide: SlideIdentifier | None = None
    detector: str = "rules"
    latency_ms: int | None = None

@dataclass(frozen=True, slots=True)
class DeicticExpressionDismissed(DomainEvent):

    text: str = ""
    reason: str = ""

@dataclass(frozen=True, slots=True)
class ClarificationRequested(DomainEvent):
    clarification_id: ClarificationId | None = None
    slide: SlideIdentifier | None = None
    pointed_element: str = ""

@dataclass(frozen=True, slots=True)
class ClarificationReady(DomainEvent):

    clarification_id: ClarificationId | None = None
    slide: SlideIdentifier | None = None
    text: str = ""
    is_stale: bool = False
    latency_ms: int | None = None

@dataclass(frozen=True, slots=True)
class ClarificationFailed(DomainEvent):
    clarification_id: ClarificationId | None = None
    slide: SlideIdentifier | None = None
    status: ClarificationStatus = ClarificationStatus.FAILED
    error: str = ""

@dataclass(frozen=True, slots=True)
class ClarificationListened(DomainEvent):
    clarification_id: ClarificationId | None = None

@dataclass(frozen=True, slots=True)
class SlideTagInserted(DomainEvent):
    entry_id: NoteEntryId | None = None
    slide: SlideIdentifier | None = None
    scheduled: bool = False

@dataclass(frozen=True, slots=True)
class ClarificationInsertedIntoNotes(DomainEvent):
    entry_id: NoteEntryId | None = None
    clarification_id: ClarificationId | None = None
    slide: SlideIdentifier | None = None

@dataclass(frozen=True, slots=True)
class NotesUpdated(DomainEvent):
    entry_count: int = 0
    restored_markers: tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True, slots=True)
class NotesExported(DomainEvent):
    fmt: str = ""
    processed: bool = False
    entry_count: int = 0
