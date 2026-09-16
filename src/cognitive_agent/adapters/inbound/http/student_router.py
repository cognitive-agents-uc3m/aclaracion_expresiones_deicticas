from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from ....application.dto import (
    ExportNotesCommand,
    InsertClarificationCommand,
    UpdateNotesCommand,
)
from ....domain.value_objects.identifiers import ClarificationId
from ....infrastructure.dependency_injection.container import Container
from .dependencies import get_container, session_id_of
from .schemas import (
    InsertClarificationBody,
    JumpBody,
    NotesBody,
    clarification_payload,
    notes_payload,
    session_payload,
    slide_payload,
)

router = APIRouter(prefix="/api/student", tags=["alumno"])

@router.get("/sessions/{session_id}/state")
def get_state(session_id: str, container: Container = Depends(get_container)):

    sid = session_id_of(session_id)
    session = container.get_session.execute(sid)
    notes = container.jump_to_slide_notes
    del notes
    return {
        **session_payload(session),
        "notifications": _drain(container, sid),
        "shortcuts": container.settings.accessibility.shortcuts,
        "auto_play": container.settings.clarification.auto_play,
    }

@router.get("/sessions/{session_id}/slide")
def get_slide(session_id: str, container: Container = Depends(get_container)):
    return slide_payload(container.get_current_slide.execute(session_id_of(session_id)))

@router.get("/sessions/{session_id}/clarification")
def get_clarification(session_id: str, container: Container = Depends(get_container)):
    view = container.get_latest_clarification.execute(session_id_of(session_id))
    return {"clarification": clarification_payload(view)}

@router.post("/sessions/{session_id}/clarification/listen")
def listen_clarification(
    session_id: str,
    clarification_id: str | None = None,
    container: Container = Depends(get_container),
):

    output = container.listen_clarification.execute(
        session_id_of(session_id),
        clarification_id=ClarificationId(clarification_id) if clarification_id else None,
    )
    if output.is_client_side:
        return {
            "mode": "client",
            "text": output.text,
            "provider": output.provider,
            "language": getattr(container.tts, "language", "es-ES"),
        }
    return Response(content=output.audio, media_type=output.mime_type or "audio/wav")

@router.post("/sessions/{session_id}/clarification/insert")
def insert_clarification(
    session_id: str,
    body: InsertClarificationBody | None = None,
    container: Container = Depends(get_container),
):

    payload = body or InsertClarificationBody()
    view = container.insert_clarification.execute(
        InsertClarificationCommand(
            session_id=session_id_of(session_id),
            clarification_id=(
                ClarificationId(payload.clarification_id) if payload.clarification_id else None
            ),
            requested_by_student=True,
        )
    )
    return notes_payload(view)

@router.put("/sessions/{session_id}/notes")
def update_notes(
    session_id: str, body: NotesBody, container: Container = Depends(get_container)
):
    view = container.update_notes.execute(
        UpdateNotesCommand(
            session_id=session_id_of(session_id),
            text=body.text,
            is_keystroke=body.is_keystroke,
        )
    )
    return notes_payload(view)

@router.get("/sessions/{session_id}/notes")
def get_notes(session_id: str, container: Container = Depends(get_container)):
    notes = container.notes.get_or_create(session_id_of(session_id))
    from ....application.views import notes_view

    return notes_payload(notes_view(notes))

@router.post("/sessions/{session_id}/notes/jump")
def jump_to_slide(
    session_id: str, body: JumpBody | None = None, container: Container = Depends(get_container)
):
    payload = body or JumpBody()
    view = container.jump_to_slide_notes.execute(
        session_id_of(session_id), slide_index=payload.slide_index
    )
    return notes_payload(view)

@router.get("/sessions/{session_id}/notes/export")
def export_notes(
    session_id: str,
    fmt: str = "text",
    processed: bool = False,
    container: Container = Depends(get_container),
):
    document = container.export_notes.execute(
        ExportNotesCommand(session_id=session_id_of(session_id), fmt=fmt, processed=processed)
    )
    return Response(
        content=document.content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',

            "X-Notes-Processed": "1" if document.processed else "0",
        },
    )

@router.get("/sessions/{session_id}/notifications")
def get_notifications(session_id: str, container: Container = Depends(get_container)):

    return {"notifications": _drain(container, session_id_of(session_id))}

def _drain(container: Container, session_id) -> list[dict]:
    hub = getattr(container, "live_region", None)
    if hub is None:
        return []
    from ....adapters.outbound.notifications import LiveRegionNotificationHub

    return [LiveRegionNotificationHub.to_payload(n) for n in hub.drain(session_id)]
