from __future__ import annotations

from ..domain.entities.clarification import Clarification
from ..domain.entities.classroom_session import ClassroomSession
from ..domain.entities.student_notes import StudentNotes
from ..domain.value_objects.identifiers import SlideIdentifier
from ..domain.value_objects.slide_description import SlideDescription
from .dto import ClarificationView, NotesView, SessionView, SlideView

def slide_view(
    session: ClassroomSession,
    description: SlideDescription | None = None,
) -> SlideView:
    slide = session.current_slide
    if slide is None or not session.has_deck:
        return SlideView(index=0, number=0, count=0, label="Sin presentacion")

    ready = description is not None and description.is_ready
    return SlideView(
        index=slide.index,
        number=slide.number,
        count=session.slide_count,
        label=session.slide_label,
        has_description=description is not None,
        description=description.content if ready and description else "",
        description_format=description.fmt.value if description else "text",
        description_ready=ready,
    )

def clarification_view(
    clarification: Clarification | None,
    *,
    current_slide: SlideIdentifier | None = None,
) -> ClarificationView | None:
    if clarification is None:
        return None
    return ClarificationView(
        clarification_id=clarification.clarification_id.value,
        text=clarification.text,
        slide_number=clarification.slide.number,
        slide_index=clarification.slide.index,
        status=clarification.status.value,
        created_at=clarification.requested_at,
        is_stale=clarification.is_stale_for(current_slide),
        listened=clarification.listened,
        inserted=clarification.inserted_into_notes,
        model=clarification.model,
        prompt_version=str(clarification.prompt_ref) if clarification.prompt_ref else "",
        latency_ms=clarification.latency_ms,
        trigger_expression=(
            clarification.trigger_expression.surface if clarification.trigger_expression else ""
        ),
        trigger_fragment=clarification.trigger_fragment,
    )

def notes_view(
    notes: StudentNotes,
    *,
    caret_offset: int | None = None,
    restored_markers: tuple[str, ...] = (),
    inserted_markers: tuple[str, ...] = (),
    announcement: str = "",
) -> NotesView:
    current = notes.current_slide
    return NotesView(
        text=notes.render_raw(),
        entry_count=len(notes.entries),
        current_slide_number=current.number if current else None,
        outline=tuple(notes.outline()),
        caret_offset=caret_offset,
        restored_markers=restored_markers,
        inserted_markers=inserted_markers,
        announcement=announcement,
    )

def session_view(
    session: ClassroomSession,
    *,
    description: SlideDescription | None = None,
    latest: Clarification | None = None,
) -> SessionView:
    return SessionView(
        session_id=session.session_id.value,
        subject=session.subject.value,
        title=session.title,
        is_active=session.is_active,
        slide=slide_view(session, description),
        started_at=session.started_at,
        ended_at=session.ended_at,
        latest_clarification=clarification_view(latest, current_slide=session.current_slide),
    )
