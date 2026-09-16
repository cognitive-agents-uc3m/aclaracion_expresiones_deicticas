from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..value_objects.content_source import ContentSource
from ..value_objects.identifiers import ClarificationId, NoteEntryId, SessionId, SlideIdentifier
from ..value_objects.tags import (
    DEFAULT_CLARIFICATION_TAG_TEMPLATE,
    DEFAULT_SLIDE_TAG_TEMPLATE,
    ClarificationTag,
    SlideTag,
)
from .note_entry import (
    ClarificationNoteEntry,
    NoteEntry,
    NoteEntryKind,
    SlideTagNoteEntry,
    TextNoteEntry,
)

@dataclass
class StudentNotes:

    session_id: SessionId
    entries: list[NoteEntry] = field(default_factory=list)
    slide_tag_template: str = DEFAULT_SLIDE_TAG_TEMPLATE
    clarification_tag_template: str = DEFAULT_CLARIFICATION_TAG_TEMPLATE
    _next_sequence: int = 0

    @property
    def is_empty(self) -> bool:
        return not any(e.render().strip() for e in self.entries)

    @property
    def has_student_content(self) -> bool:
        return any(
            isinstance(e, TextNoteEntry) and not e.is_blank for e in self.entries
        )

    @property
    def last_entry(self) -> NoteEntry | None:
        return self.entries[-1] if self.entries else None

    @property
    def current_slide(self) -> SlideIdentifier | None:

        for entry in reversed(self.entries):
            if isinstance(entry, SlideTagNoteEntry) and entry.slide is not None:
                return entry.slide
        return None

    def has_clarification(self, clarification_id: ClarificationId) -> bool:
        return any(
            isinstance(e, ClarificationNoteEntry) and e.clarification_id == clarification_id
            for e in self.entries
        )

    def text_entries(self) -> list[TextNoteEntry]:
        return [e for e in self.entries if isinstance(e, TextNoteEntry)]

    def system_entries(self) -> list[NoteEntry]:
        return [e for e in self.entries if e.kind is not NoteEntryKind.TEXT]

    def _next_seq(self) -> int:
        seq = self._next_sequence
        self._next_sequence += 1
        return seq

    def append_student_text(
        self, text: str, *, at: datetime, slide: SlideIdentifier | None = None
    ) -> TextNoteEntry:
        entry = TextNoteEntry(
            entry_id=NoteEntryId.new(),
            sequence=self._next_seq(),
            created_at=at,
            source=ContentSource.STUDENT,
            slide=slide if slide is not None else self.current_slide,
            text=text,
        )
        self.entries.append(entry)
        return entry

    def insert_slide_tag(
        self, slide: SlideIdentifier, *, at: datetime
    ) -> SlideTagNoteEntry | None:

        last_significant = next(
            (e for e in reversed(self.entries) if e.render().strip()), None
        )
        if (
            isinstance(last_significant, SlideTagNoteEntry)
            and last_significant.slide == slide
        ):
            return None

        entry = SlideTagNoteEntry(
            entry_id=NoteEntryId.new(),
            sequence=self._next_seq(),
            created_at=at,
            source=ContentSource.SYSTEM,
            slide=slide,
            tag=SlideTag(slide=slide, template=self.slide_tag_template),
        )
        self.entries.append(entry)
        return entry

    def insert_slide_tag_at_start(
        self, slide: SlideIdentifier, *, at: datetime
    ) -> SlideTagNoteEntry | None:

        if self.system_entries():
            return None

        entry = SlideTagNoteEntry(
            entry_id=NoteEntryId.new(),
            sequence=-1,
            created_at=at,
            source=ContentSource.SYSTEM,
            slide=slide,
            tag=SlideTag(slide=slide, template=self.slide_tag_template),
        )
        self.entries.insert(0, entry)
        self._renumber()
        return entry

    def _renumber(self) -> None:
        from dataclasses import replace as _replace

        self.entries = [_replace(e, sequence=i) for i, e in enumerate(self.entries)]
        self._next_sequence = len(self.entries)

    def insert_clarification(
        self,
        *,
        clarification_id: ClarificationId,
        slide: SlideIdentifier,
        text: str,
        at: datetime,
    ) -> ClarificationNoteEntry | None:

        if self.has_clarification(clarification_id):
            return None

        entry = ClarificationNoteEntry(
            entry_id=NoteEntryId.new(),
            sequence=self._next_seq(),
            created_at=at,
            source=ContentSource.LLM,
            slide=slide,
            tag=ClarificationTag(
                slide=slide, text=text, template=self.clarification_tag_template
            ),
            clarification_id=clarification_id,
        )
        self.entries.append(entry)
        return entry

    def replace_entries(self, entries: list[NoteEntry]) -> None:

        self.entries = list(entries)
        self._next_sequence = max((e.sequence for e in entries), default=-1) + 1

    def render_raw(self) -> str:

        parts: list[str] = []
        for entry in self.entries:
            block = entry.render()
            if entry.kind is NoteEntryKind.TEXT:
                if not block:
                    continue
                parts.append(block)
            else:
                if parts:
                    parts.append("")
                parts.append(block)
        return "\n".join(parts)

    def student_text_only(self) -> str:

        return "\n".join(e.text for e in self.text_entries() if e.text)

    def outline(self) -> list[tuple[int, str, str]]:

        return [
            (e.sequence, e.kind.value, e.accessible_label)
            for e in self.entries
            if e.kind is not NoteEntryKind.TEXT
        ]

    @staticmethod
    def empty(
        session_id: SessionId,
        *,
        slide_tag_template: str = DEFAULT_SLIDE_TAG_TEMPLATE,
        clarification_tag_template: str = DEFAULT_CLARIFICATION_TAG_TEMPLATE,
    ) -> "StudentNotes":
        return StudentNotes(
            session_id=session_id,
            slide_tag_template=slide_tag_template,
            clarification_tag_template=clarification_tag_template,
        )
