from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from ..entities.note_entry import NoteEntry, NoteEntryKind, TextNoteEntry
from ..entities.student_notes import StudentNotes
from ..value_objects.content_source import ContentSource
from ..value_objects.identifiers import NoteEntryId, SlideIdentifier

_ANCHOR_LEN = 60
_ANCHOR_MIN = 8

@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    changed: bool = False
    restored_markers: tuple[str, ...] = field(default_factory=tuple)

    rendered: str = ""

    @property
    def repaired(self) -> bool:
        return bool(self.restored_markers)

def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")

def _anchor_of(entries: list[TextNoteEntry]) -> str:

    for entry in entries:
        stripped = entry.text.strip()
        if len(stripped) >= _ANCHOR_MIN:
            return stripped[:_ANCHOR_LEN]
    return ""

class NotesProjection:

    @staticmethod
    def render(notes: StudentNotes) -> str:
        return notes.render_raw()

    @staticmethod
    def group_text_entries(notes: StudentNotes) -> list[list[TextNoteEntry]]:

        groups: list[list[TextNoteEntry]] = [[]]
        for entry in notes.entries:
            if entry.kind is NoteEntryKind.TEXT:
                assert isinstance(entry, TextNoteEntry)
                groups[-1].append(entry)
            else:
                groups.append([])
        return groups

    @classmethod
    def reconcile(
        cls, notes: StudentNotes, incoming_text: str, *, at: datetime
    ) -> ReconciliationResult:

        text = _normalize_newlines(incoming_text)
        system = notes.system_entries()
        groups = cls.group_text_entries(notes)

        segments: list[str] = []
        restored: list[str] = []
        cursor = 0

        for index, system_entry in enumerate(system):
            block = system_entry.render()
            position = text.find(block, cursor)
            if position >= 0:
                segments.append(text[cursor:position])
                cursor = position + len(block)
                continue

            anchor = _anchor_of(groups[index + 1]) if index + 1 < len(groups) else ""
            anchor_pos = text.find(anchor, cursor) if anchor else -1
            if anchor_pos >= 0:
                segments.append(text[cursor:anchor_pos])
                cursor = anchor_pos
            elif not groups[index]:

                segments.append("")
            else:
                segments.append(text[cursor:])
                cursor = len(text)
            restored.append(block)

        segments.append(text[cursor:])

        rebuilt: list[NoteEntry] = []
        changed = bool(restored)

        for index, segment in enumerate(segments):
            body = segment.strip("\n")
            existing = groups[index] if index < len(groups) else []
            if body:
                if existing:
                    template = existing[0]
                    if template.text != body:
                        changed = True
                    rebuilt.append(template.with_text(body))
                else:
                    changed = True
                    rebuilt.append(
                        TextNoteEntry(
                            entry_id=NoteEntryId.new(),
                            sequence=0,
                            created_at=at,
                            source=ContentSource.STUDENT,
                            slide=cls._slide_before(system, index),
                            text=body,
                        )
                    )
                if len(existing) > 1:
                    changed = True
            elif existing:
                changed = True

            if index < len(system):
                rebuilt.append(system[index])

        renumbered = [replace(entry, sequence=i) for i, entry in enumerate(rebuilt)]
        notes.replace_entries(renumbered)

        return ReconciliationResult(
            changed=changed,
            restored_markers=tuple(restored),
            rendered=notes.render_raw(),
        )

    @staticmethod
    def _slide_before(system: list[NoteEntry], group_index: int) -> SlideIdentifier | None:
        if group_index == 0 or not system:
            return None
        return system[min(group_index, len(system)) - 1].slide

    @staticmethod
    def caret_offset_for_slide(notes: StudentNotes, slide: SlideIdentifier) -> int | None:

        rendered = notes.render_raw()
        target_index: int | None = None
        for position, entry in enumerate(notes.entries):
            if entry.kind is NoteEntryKind.SLIDE_TAG and entry.slide == slide:
                target_index = position

        if target_index is None:
            return None

        partial = StudentNotes(
            session_id=notes.session_id,
            entries=list(notes.entries[: _block_end(notes, target_index)]),
            slide_tag_template=notes.slide_tag_template,
            clarification_tag_template=notes.clarification_tag_template,
        )
        offset = len(partial.render_raw())
        return min(offset, len(rendered))

def _block_end(notes: StudentNotes, tag_index: int) -> int:

    for position in range(tag_index + 1, len(notes.entries)):
        if notes.entries[position].kind is NoteEntryKind.SLIDE_TAG:
            return position
    return len(notes.entries)
