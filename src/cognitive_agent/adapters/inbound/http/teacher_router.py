from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from ....application.dto import (
    AudioChunk,
    ChangeSlideCommand,
    LoadDeckCommand,
    RenameSessionCommand,
    StartSessionCommand,
    TranscriptFragmentCommand,
)
from ....domain.value_objects.subject import Subject
from ....infrastructure.dependency_injection.container import Container
from .dependencies import get_container, session_id_of
from .schemas import (
    ChangeSlideBody,
    LoadDeckBody,
    RenameSessionBody,
    StartSessionBody,
    TranscriptBody,
    fragment_payload,
    session_payload,
    slide_payload,
)

router = APIRouter(prefix="/api/teacher", tags=["profesor"])

@router.post("/sessions", status_code=201)
def start_session(body: StartSessionBody, container: Container = Depends(get_container)):
    view = container.start_session.execute(
        StartSessionCommand(
            subject=Subject.parse(body.subject),
            title=body.title,
            access_key=body.access_key,
        )
    )
    return session_payload(view)

@router.get("/sessions/{session_id}")
def get_session(session_id: str, container: Container = Depends(get_container)):
    return session_payload(container.get_session.execute(session_id_of(session_id)))

@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: str, body: RenameSessionBody, container: Container = Depends(get_container)
):

    view = container.rename_session.execute(
        RenameSessionCommand(session_id=session_id_of(session_id), title=body.title)
    )
    return session_payload(view)

@router.post("/sessions/{session_id}/end")
def end_session(session_id: str, container: Container = Depends(get_container)):
    return session_payload(container.end_session.execute(session_id_of(session_id)))

@router.post("/sessions/{session_id}/deck")
def load_deck(session_id: str, body: LoadDeckBody, container: Container = Depends(get_container)):
    view = container.load_deck.execute(
        LoadDeckCommand(
            session_id=session_id_of(session_id),
            deck_id=body.deck_id,
            slide_count=body.slide_count,
            title=body.title,
            source_name=body.source_name,
        )
    )
    return slide_payload(view)

@router.post("/sessions/{session_id}/slide")
def change_slide(
    session_id: str, body: ChangeSlideBody, container: Container = Depends(get_container)
):
    view = container.change_slide.execute(
        ChangeSlideCommand(
            session_id=session_id_of(session_id), index=body.index, delta=body.delta
        )
    )
    return slide_payload(view)

@router.post("/sessions/{session_id}/slide/next")
def next_slide(session_id: str, container: Container = Depends(get_container)):
    view = container.change_slide.execute(
        ChangeSlideCommand(session_id=session_id_of(session_id), delta=1)
    )
    return slide_payload(view)

@router.post("/sessions/{session_id}/slide/previous")
def previous_slide(session_id: str, container: Container = Depends(get_container)):
    view = container.change_slide.execute(
        ChangeSlideCommand(session_id=session_id_of(session_id), delta=-1)
    )
    return slide_payload(view)

@router.post("/sessions/{session_id}/transcript")
def submit_transcript(
    session_id: str, body: TranscriptBody, container: Container = Depends(get_container)
):

    result = container.process_fragment.execute(
        TranscriptFragmentCommand(session_id=session_id_of(session_id), text=body.text)
    )
    return fragment_payload(result)

@router.post("/sessions/{session_id}/audio")
async def submit_audio(
    session_id: str,
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
):

    data = await file.read()
    result = container.process_fragment.execute(
        TranscriptFragmentCommand(
            session_id=session_id_of(session_id),
            audio=AudioChunk(
                data=data, mime_type=file.content_type or "audio/wav"
            ),
        )
    )
    return fragment_payload(result)

@router.post("/sessions/{session_id}/deck/upload")
async def upload_deck(
    session_id: str,
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
):

    import tempfile
    from pathlib import Path

    if container.documents is None:
        raise HTTPException(
            status_code=501,
            detail="La subida de PDF requiere el extra [documents] (PyMuPDF).",
        )

    sid = session_id_of(session_id)
    session = container.sessions.require(sid)

    suffix = Path(file.filename or "presentacion.pdf").suffix or ".pdf"
    destination = Path(tempfile.gettempdir()) / f"ca_deck_{sid.value}{suffix}"
    destination.write_bytes(await file.read())

    info = container.documents.open_deck(destination, profile=session.subject.value)
    view = container.load_deck.execute(
        LoadDeckCommand(
            session_id=sid,
            deck_id=info.deck_id,
            slide_count=info.slide_count,
            title=info.title,

            source_name=info.path,
        )
    )

    progress = None
    if container.precompute is not None:
        progress = container.precompute.enqueue(
            deck_id=info.deck_id,
            slide_count=info.slide_count,
            document_path=info.path,
            subject=session.subject,
        )

    return {
        **slide_payload(view),
        "deck_id": info.deck_id,
        "precompute": (
            {"percent": progress.percent, "status": progress.as_text()} if progress else None
        ),
    }

@router.get("/sessions/{session_id}/slide/image")
def slide_image(session_id: str, container: Container = Depends(get_container)):

    from fastapi.responses import FileResponse

    sesion = container.sessions.require(session_id_of(session_id))
    if container.documents is None or sesion.deck is None or sesion.current_slide is None:
        raise HTTPException(status_code=404, detail="No hay diapositiva que mostrar.")
    try:
        ruta = container.documents.render_slide(
            sesion.deck.source_name, sesion.current_slide.index
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No se pudo renderizar: {exc}") from exc
    return FileResponse(ruta, media_type="image/png")

@router.post("/sessions/{session_id}/pointer")
async def update_pointer(
    session_id: str, request: Request, container: Container = Depends(get_container)
):

    cuerpo = await request.json()
    try:
        x = float(cuerpo.get("x"))
        y = float(cuerpo.get("y"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Coordenadas no validas.") from None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return {"ok": False, "detail": "Fuera de la diapositiva."}

    sid = session_id_of(session_id)
    with container.sessions.transaction(sid) as sesion:
        posicion = sesion.point_at(x, y, at=container.clock.now())
    return {"ok": posicion is not None}

@router.get("/sessions/{session_id}/precompute")
def precompute_status(session_id: str, container: Container = Depends(get_container)):
    sid = session_id_of(session_id)
    session = container.sessions.require(sid)
    if container.precompute is None or session.deck is None:
        return {"available": False, "percent": 0.0, "status": "Preproceso no disponible."}
    progress = container.precompute.progress(
        session.deck.deck_id.value, session.deck.slide_count
    )
    return {
        "available": True,
        "percent": progress.percent,
        "ready": progress.ready,
        "failed": progress.failed,
        "pending": progress.pending,
        "total": progress.total,
        "complete": progress.is_complete,
        "status": progress.as_text(),
    }

@router.post("/sessions/{session_id}/precompute/retry")
def precompute_retry(session_id: str, container: Container = Depends(get_container)):
    sid = session_id_of(session_id)
    session = container.sessions.require(sid)
    if container.precompute is None or session.deck is None:
        raise HTTPException(status_code=409, detail="No hay presentacion que reprocesar.")
    progress = container.precompute.enqueue(
        deck_id=session.deck.deck_id.value,
        slide_count=session.deck.slide_count,
        document_path=session.deck.source_name,
        subject=session.subject,
        only_failed=True,
    )
    return {"percent": progress.percent, "status": progress.as_text()}

@router.get("/prompts")
def list_prompts(container: Container = Depends(get_container)):

    available = container.prompts.available()
    subjects = {}
    for name in available:
        getter = getattr(container.prompts, "subjects_for", None)
        subjects[name] = getter(name) if callable(getter) else []
    return {"prompts": available, "subjects": subjects}

@router.get("/prompts/{name}")
def get_prompt(
    name: str,
    subject: str = "generic",
    version: str | None = None,
    container: Container = Depends(get_container),
):
    raw = getattr(container.prompts, "raw_text", None)
    parsed_subject = Subject.parse(subject)
    ref = container.prompts.ref(name, subject=parsed_subject, version=version)
    return {
        "name": name,
        "subject": parsed_subject.value,
        "version": ref.version,
        "reference": str(ref),
        "text": raw(name, subject=parsed_subject, version=version) if callable(raw) else "",
    }
