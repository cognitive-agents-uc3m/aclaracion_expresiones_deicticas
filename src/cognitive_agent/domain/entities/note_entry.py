from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from ..value_objects.content_source import ContentSource
from ..value_objects.identifiers import ClarificationId, NoteEntryId, SlideIdentifier
from ..value_objects.tags import ClarificationTag, SlideTag

class NoteEntryKind(str, Enum):
    TEXT = "text"
    SLIDE_TAG = "slide_tag"
    CLARIFICATION = "clarification"

@dataclass(frozen=True)
class NoteEntry:

    entry_id: NoteEntryId
    sequence: int
    created_at: datetime
    source: ContentSource
    slide: SlideIdentifier | None = None

    @property
    def kind(self) -> NoteEntryKind:
        raise NotImplementedError

    def render(self) -> str:
        raise NotImplementedError

    @property
    def is_student_owned(self) -> bool:

        return self.source.is_editable_by_student

    @property
    def starts_block(self) -> bool:

        return self.kind is not NoteEntryKind.TEXT

    @property
    def accessible_label(self) -> str:
        raise NotImplementedError

@dataclass(frozen=True)
class TextNoteEntry(NoteEntry):

    text: str = ""

    @property
    def kind(self) -> NoteEntryKind:
        return NoteEntryKind.TEXT

    def render(self) -> str:
        return self.text

    @property
    def is_blank(self) -> bool:
        return not self.text.strip()

    def with_text(self, text: str) -> "TextNoteEntry":
        return replace(self, text=text)

    @property
    def accessible_label(self) -> str:
        preview = " ".join(self.text.split())[:40]
        return f"Apunte: {preview}" if preview else "Apunte vacio"

@dataclass(frozen=True)
class SlideTagNoteEntry(NoteEntry):

    tag: SlideTag | None = None

    def __post_init__(self) -> None:
        if self.tag is None:
            raise ValueError("SlideTagNoteEntry requiere una etiqueta.")

    @property
    def kind(self) -> NoteEntryKind:
        return NoteEntryKind.SLIDE_TAG

    def render(self) -> str:
        assert self.tag is not None
        return self.tag.render()

    @property
    def accessible_label(self) -> str:
        assert self.tag is not None
        return self.tag.accessible_label

@dataclass(frozen=True)
class ClarificationNoteEntry(NoteEntry):

    tag: ClarificationTag | None = None
    clarification_id: ClarificationId | None = None

    def __post_init__(self) -> None:
        if self.tag is None:
            raise ValueError("ClarificationNoteEntry requiere una etiqueta.")

    @property
    def kind(self) -> NoteEntryKind:
        return NoteEntryKind.CLARIFICATION

    def render(self) -> str:
        assert self.tag is not None
        return self.tag.render()

    @property
    def accessible_label(self) -> str:
        assert self.tag is not None
        return self.tag.accessible_label
