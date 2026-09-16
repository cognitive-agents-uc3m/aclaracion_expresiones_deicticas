from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...dto import (
    ChangeSlideCommand,
    ExportedNotes,
    ExportNotesCommand,
    InsertClarificationCommand,
    LoadDeckCommand,
    NotesView,
    ProcessFragmentResult,
    SessionView,
    SlideView,
    SpeechOutput,
    StartSessionCommand,
    TranscriptFragmentCommand,
    UpdateNotesCommand,
)
from ...dto import ClarificationView as _ClarificationView
from ....domain.value_objects.identifiers import SessionId

@runtime_checkable
class TeacherSessionPort(Protocol):

    def start_session(self, command: StartSessionCommand) -> SessionView: ...

    def end_session(self, session_id: SessionId) -> SessionView: ...

    def load_deck(self, command: LoadDeckCommand) -> SlideView: ...

    def change_slide(self, command: ChangeSlideCommand) -> SlideView: ...

@runtime_checkable
class TranscriptIngestionPort(Protocol):

    def submit_fragment(self, command: TranscriptFragmentCommand) -> ProcessFragmentResult: ...

@runtime_checkable
class StudentNotebookPort(Protocol):

    def update_notes(self, command: UpdateNotesCommand) -> NotesView: ...

    def insert_clarification(self, command: InsertClarificationCommand) -> NotesView: ...

    def jump_to_slide_notes(self, session_id: SessionId, *, slide_index: int | None = None) -> NotesView: ...

    def listen_latest_clarification(self, session_id: SessionId) -> SpeechOutput: ...

    def export_notes(self, command: ExportNotesCommand) -> ExportedNotes: ...

@runtime_checkable
class SessionQueryPort(Protocol):

    def get_session(self, session_id: SessionId) -> SessionView: ...

    def get_current_slide(self, session_id: SessionId) -> SlideView: ...

    def get_latest_clarification(self, session_id: SessionId) -> _ClarificationView | None: ...

    def get_notes(self, session_id: SessionId) -> NotesView: ...

__all__ = [
    "SessionQueryPort",
    "StudentNotebookPort",
    "TeacherSessionPort",
    "TranscriptIngestionPort",
]
