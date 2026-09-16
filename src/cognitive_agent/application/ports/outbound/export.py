from __future__ import annotations

from typing import Protocol, runtime_checkable

from ....domain.entities.student_notes import StudentNotes
from ...dto import ExportedNotes

@runtime_checkable
class NotesExporterPort(Protocol):

    fmt: str
    mime_type: str
    extension: str

    def export(
        self,
        notes: StudentNotes,
        *,
        title: str = "",
        processed_text: str | None = None,
    ) -> ExportedNotes:

        ...
