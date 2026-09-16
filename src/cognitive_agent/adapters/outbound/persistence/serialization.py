from __future__ import annotations

from datetime import datetime
from typing import Any

from ....domain.entities.clarification import Clarification, ClarificationStatus
from ....domain.entities.classroom_session import ClassroomSession
from ....domain.entities.note_entry import (
    ClarificationNoteEntry,
    NoteEntry,
    SlideTagNoteEntry,
    TextNoteEntry,
)
from ....domain.entities.slide import Deck
from ....domain.entities.student_interaction_state import (
    PendingSlideTransition,
    StudentInteractionState,
)
from ....domain.entities.student_notes import StudentNotes
from ....domain.value_objects.content_source import ContentSource
from ....domain.value_objects.deictic import DeicticExpression, DeicticKind
from ....domain.value_objects.identifiers import (
    ClarificationId,
    DeckId,
    NoteEntryId,
    SessionId,
    SlideIdentifier,
)
from ....domain.value_objects.pointer import PointerPosition
from ....domain.value_objects.prompt import PromptRef
from ....domain.value_objects.subject import Subject
from ....domain.value_objects.tags import ClarificationTag, SlideTag
from ....domain.value_objects.transcript import TranscriptContext, TranscriptFragment

SCHEMA_VERSION = 1

def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None

def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))

def _slide(slide: SlideIdentifier | None) -> dict | None:
    if slide is None:
        return None
    return {"deck_id": slide.deck_id.value, "index": slide.index}

def _parse_slide(data: Any) -> SlideIdentifier | None:
    if not data:
        return None
    return SlideIdentifier(DeckId(str(data["deck_id"])), int(data["index"]))

def session_to_dict(session: ClassroomSession) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "session_id": session.session_id.value,
        "subject": session.subject.value,
        "started_at": _dt(session.started_at),
        "ended_at": _dt(session.ended_at),
        "access_key": session.access_key,
        "title": session.title,
        "version": session.version,
        "latest_clarification_id": (
            session.latest_clarification_id.value if session.latest_clarification_id else None
        ),
        "deck": (
            {
                "deck_id": session.deck.deck_id.value,
                "slide_count": session.deck.slide_count,
                "title": session.deck.title,
                "source_name": session.deck.source_name,
            }
            if session.deck
            else None
        ),
        "current_slide": _slide(session.current_slide),
        "pointer": (
            {
                "x": session.pointer.x,
                "y": session.pointer.y,
                "at": _dt(session.pointer.at),
                "slide": _slide(session.pointer.slide),
            }
            if session.pointer
            else None
        ),
        "context": {
            "max_size": session.context.max_size,
            "fragments": [
                {
                    "text": f.text,
                    "received_at": _dt(f.received_at),
                    "slide": _slide(f.slide),
                    "source": f.source.value,
                }
                for f in session.context.fragments
            ],
        },
        "interaction": {
            "last_keystroke_at": _dt(session.interaction.last_keystroke_at),
            "caret_slide": _slide(session.interaction.caret_slide),
            "pending_transition": (
                {
                    "slide": _slide(session.interaction.pending_transition.slide),
                    "requested_at": _dt(session.interaction.pending_transition.requested_at),
                    "deadline": _dt(session.interaction.pending_transition.deadline),
                }
                if session.interaction.pending_transition
                else None
            ),
        },
    }

def session_from_dict(data: dict) -> ClassroomSession:
    session_id = SessionId(str(data["session_id"]))
    deck_data = data.get("deck")
    deck = (
        Deck(
            deck_id=DeckId(str(deck_data["deck_id"])),
            slide_count=int(deck_data["slide_count"]),
            title=deck_data.get("title", ""),
            source_name=deck_data.get("source_name", ""),
        )
        if deck_data
        else None
    )

    context_data = data.get("context") or {}
    fragments = tuple(
        TranscriptFragment(
            text=f["text"],
            received_at=_parse_dt(f.get("received_at")) or datetime.min,
            session_id=session_id,
            slide=_parse_slide(f.get("slide")),
            source=ContentSource(f.get("source", ContentSource.TEACHER.value)),
        )
        for f in context_data.get("fragments", [])
    )

    interaction_data = data.get("interaction") or {}
    pending_data = interaction_data.get("pending_transition")
    pending = (
        PendingSlideTransition(
            slide=_parse_slide(pending_data["slide"]),
            requested_at=_parse_dt(pending_data["requested_at"]),
            deadline=_parse_dt(pending_data["deadline"]),
        )
        if pending_data
        else None
    )

    pointer_data = data.get("pointer")
    pointer = None
    if pointer_data:
        try:
            pointer = PointerPosition(
                x=float(pointer_data["x"]),
                y=float(pointer_data["y"]),
                at=_parse_dt(pointer_data["at"]),
                slide=_parse_slide(pointer_data["slide"]),
            )
        except (KeyError, TypeError, ValueError):
            pointer = None

    latest = data.get("latest_clarification_id")
    return ClassroomSession(
        session_id=session_id,
        subject=Subject.parse(data.get("subject")),
        started_at=_parse_dt(data.get("started_at")) or datetime.min,
        access_key=data.get("access_key", ""),
        title=data.get("title", ""),
        deck=deck,
        current_slide=_parse_slide(data.get("current_slide")),
        context=TranscriptContext(
            fragments=fragments, max_size=int(context_data.get("max_size", 3))
        ),
        interaction=StudentInteractionState(
            last_keystroke_at=_parse_dt(interaction_data.get("last_keystroke_at")),
            pending_transition=pending,
            caret_slide=_parse_slide(interaction_data.get("caret_slide")),
        ),
        latest_clarification_id=ClarificationId(str(latest)) if latest else None,
        pointer=pointer,
        ended_at=_parse_dt(data.get("ended_at")),
        version=int(data.get("version", 0)),
    )

def note_entry_to_dict(entry: NoteEntry) -> dict:
    payload: dict = {
        "kind": entry.kind.value,
        "entry_id": entry.entry_id.value,
        "sequence": entry.sequence,
        "created_at": _dt(entry.created_at),
        "source": entry.source.value,
        "slide": _slide(entry.slide),
    }
    if isinstance(entry, TextNoteEntry):
        payload["text"] = entry.text
    elif isinstance(entry, SlideTagNoteEntry) and entry.tag:
        payload["template"] = entry.tag.template
    elif isinstance(entry, ClarificationNoteEntry) and entry.tag:
        payload["template"] = entry.tag.template
        payload["text"] = entry.tag.text
        payload["clarification_id"] = (
            entry.clarification_id.value if entry.clarification_id else None
        )
    return payload

def note_entry_from_dict(data: dict) -> NoteEntry:
    kind = data.get("kind")
    common = {
        "entry_id": NoteEntryId(str(data["entry_id"])),
        "sequence": int(data.get("sequence", 0)),
        "created_at": _parse_dt(data.get("created_at")) or datetime.min,
        "source": ContentSource(data.get("source", ContentSource.STUDENT.value)),
        "slide": _parse_slide(data.get("slide")),
    }
    if kind == "slide_tag":
        slide = common["slide"]
        return SlideTagNoteEntry(
            **common,
            tag=SlideTag(slide=slide, template=data.get("template", "[Diapositiva {number}]")),
        )
    if kind == "clarification":
        slide = common["slide"]
        clarification_id = data.get("clarification_id")
        return ClarificationNoteEntry(
            **common,
            tag=ClarificationTag(
                slide=slide,
                text=data.get("text", ""),
                template=data.get("template", "[Aclaracion - Diapositiva {number}]"),
            ),
            clarification_id=ClarificationId(str(clarification_id)) if clarification_id else None,
        )
    return TextNoteEntry(**common, text=data.get("text", ""))

def notes_to_dict(notes: StudentNotes) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "session_id": notes.session_id.value,
        "slide_tag_template": notes.slide_tag_template,
        "clarification_tag_template": notes.clarification_tag_template,
        "entries": [note_entry_to_dict(e) for e in notes.entries],
    }

def notes_from_dict(data: dict) -> StudentNotes:
    entries = [note_entry_from_dict(e) for e in data.get("entries", [])]
    notes = StudentNotes(
        session_id=SessionId(str(data["session_id"])),
        entries=entries,
        slide_tag_template=data.get("slide_tag_template", "[Diapositiva {number}]"),
        clarification_tag_template=data.get(
            "clarification_tag_template", "[Aclaracion - Diapositiva {number}]"
        ),
    )
    notes._next_sequence = max((e.sequence for e in entries), default=-1) + 1
    return notes

def clarification_to_dict(clarification: Clarification) -> dict:
    expression = clarification.trigger_expression
    return {
        "schema": SCHEMA_VERSION,
        "clarification_id": clarification.clarification_id.value,
        "session_id": clarification.session_id.value,
        "slide": _slide(clarification.slide),
        "trigger_fragment": clarification.trigger_fragment,
        "recent_context": clarification.recent_context,
        "pointed_element": clarification.pointed_element,
        "description_used": clarification.description_used,
        "trigger_expression": (
            {
                "surface": expression.surface,
                "kind": expression.kind.value,
                "start": expression.start,
                "end": expression.end,
                "confidence": expression.confidence,
            }
            if expression
            else None
        ),
        "text": clarification.text,
        "status": clarification.status.value,
        "requested_at": _dt(clarification.requested_at),
        "completed_at": _dt(clarification.completed_at),
        "prompt_ref": str(clarification.prompt_ref) if clarification.prompt_ref else None,
        "model": clarification.model,
        "latency_ms": clarification.latency_ms,
        "error": clarification.error,
        "input_tokens": clarification.input_tokens,
        "output_tokens": clarification.output_tokens,
        "listened": clarification.listened,
        "inserted_into_notes": clarification.inserted_into_notes,
    }

def clarification_from_dict(data: dict) -> Clarification:
    expression_data = data.get("trigger_expression")
    prompt_ref = data.get("prompt_ref")
    return Clarification(
        clarification_id=ClarificationId(str(data["clarification_id"])),
        session_id=SessionId(str(data["session_id"])),
        slide=_parse_slide(data.get("slide")),
        trigger_fragment=data.get("trigger_fragment", ""),
        description_used=data.get("description_used", ""),
        recent_context=data.get("recent_context", ""),
        pointed_element=data.get("pointed_element", ""),
        trigger_expression=(
            DeicticExpression(
                surface=expression_data["surface"],
                kind=DeicticKind(expression_data["kind"]),
                start=int(expression_data.get("start", 0)),
                end=int(expression_data.get("end", 0)),
                confidence=float(expression_data.get("confidence", 1.0)),
            )
            if expression_data
            else None
        ),
        text=data.get("text", ""),
        status=ClarificationStatus(data.get("status", ClarificationStatus.PENDING.value)),
        requested_at=_parse_dt(data.get("requested_at")),
        completed_at=_parse_dt(data.get("completed_at")),
        prompt_ref=PromptRef.parse(prompt_ref) if prompt_ref else None,
        model=data.get("model", ""),
        latency_ms=data.get("latency_ms"),
        error=data.get("error"),
        input_tokens=data.get("input_tokens"),
        output_tokens=data.get("output_tokens"),
        listened=bool(data.get("listened", False)),
        inserted_into_notes=bool(data.get("inserted_into_notes", False)),
    )
