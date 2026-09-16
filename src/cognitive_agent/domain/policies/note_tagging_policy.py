from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..entities.note_entry import SlideTagNoteEntry
from ..entities.student_notes import StudentNotes
from ..value_objects.identifiers import SlideIdentifier
from ..value_objects.tags import DEFAULT_SLIDE_TAG_TEMPLATE

@dataclass(frozen=True, slots=True)
class TaggingOutcome:
    inserted: SlideTagNoteEntry | None = None
    announcement: str = ""

    @property
    def did_insert(self) -> bool:
        return self.inserted is not None

class NoteTaggingPolicy:
    def __init__(self, *, template: str = DEFAULT_SLIDE_TAG_TEMPLATE, announce: bool = True) -> None:
        self._template = template
        self._announce = announce

    @property
    def template(self) -> str:
        return self._template

    def apply(
        self, *, notes: StudentNotes, slide: SlideIdentifier, at: datetime
    ) -> TaggingOutcome:

        entry = notes.insert_slide_tag(slide, at=at)
        if entry is None:
            return TaggingOutcome()

        announcement = ""
        if self._announce:
            announcement = f"Diapositiva {slide.number} marcada en tus apuntes."
        return TaggingOutcome(inserted=entry, announcement=announcement)
