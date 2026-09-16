from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..entities.clarification import Clarification
from ..entities.note_entry import ClarificationNoteEntry
from ..entities.student_notes import StudentNotes
from ..value_objects.tags import DEFAULT_CLARIFICATION_TAG_TEMPLATE

class InsertionDecision(str, Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    NOT_AVAILABLE = "not_available"

    CONSENT_REQUIRED = "consent_required"

@dataclass(frozen=True, slots=True)
class InsertionOutcome:
    decision: InsertionDecision
    entry: ClarificationNoteEntry | None = None
    announcement: str = ""

    @property
    def did_insert(self) -> bool:
        return self.decision is InsertionDecision.INSERTED

class ClarificationInsertionPolicy:
    def __init__(
        self,
        *,
        template: str = DEFAULT_CLARIFICATION_TAG_TEMPLATE,
        auto_insert: bool = False,
        announce: bool = True,
    ) -> None:
        self._template = template
        self._auto_insert = auto_insert
        self._announce = announce

    @property
    def auto_insert(self) -> bool:
        return self._auto_insert

    def apply(
        self,
        *,
        notes: StudentNotes,
        clarification: Clarification | None,
        at: datetime,
        requested_by_student: bool,
    ) -> InsertionOutcome:
        if clarification is None or not clarification.is_available:
            return InsertionOutcome(
                InsertionDecision.NOT_AVAILABLE,
                announcement="No hay ninguna aclaracion disponible todavia.",
            )

        if not requested_by_student and not self._auto_insert:
            return InsertionOutcome(InsertionDecision.CONSENT_REQUIRED)

        if notes.has_clarification(clarification.clarification_id):
            return InsertionOutcome(
                InsertionDecision.ALREADY_PRESENT,
                announcement="Esa aclaracion ya estaba en tus apuntes.",
            )

        entry = notes.insert_clarification(
            clarification_id=clarification.clarification_id,
            slide=clarification.slide,
            text=clarification.text,
            at=at,
        )
        if entry is None:
            return InsertionOutcome(InsertionDecision.ALREADY_PRESENT)

        announcement = ""
        if self._announce:
            announcement = (
                f"Aclaracion de la diapositiva {clarification.slide.number} "
                "insertada al final de tus apuntes."
            )
        return InsertionOutcome(InsertionDecision.INSERTED, entry=entry, announcement=announcement)
