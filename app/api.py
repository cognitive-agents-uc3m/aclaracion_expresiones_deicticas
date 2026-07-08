import hashlib
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from assistant.slide_knowledge import slide_knowledge_store
from .shared import shared_presentation, shared_teacher_input

logger = logging.getLogger(__name__)

def _build_sync_payload() -> dict:
    pdf_path, slide_index, slide_count, _ = shared_presentation.graph_pdf_context()
    teacher_input_seq, teacher_input_text = shared_teacher_input.snapshot()
    status_text = slide_knowledge_store.deck_status_text(pdf_path)

    pdf_token = None
    if pdf_path and os.path.exists(pdf_path):
        stat = os.stat(pdf_path)
        raw = f"{os.path.abspath(pdf_path)}|{stat.st_size}|{int(stat.st_mtime)}"
        pdf_token = hashlib.md5(raw.encode("utf-8")).hexdigest()

    with shared_presentation.lock:
        class_finished = shared_presentation.class_finished
        final_pdf_token = shared_presentation.final_pdf_token

    px, py, pts, pslide = shared_presentation.pointer_snapshot()
    if pslide is None or int(pslide) != int(slide_index):
        px = py = pts = None

    clarif_seq, clarif_text = shared_presentation.clarification_snapshot()

    return {
        "slide_index": int(slide_index),
        "slide_count": int(slide_count),
        "status": shared_presentation.status,
        "pdf_available": bool(pdf_path and os.path.exists(pdf_path)),
        "pdf_token": pdf_token,
        "precompute_status": status_text,
        "teacher_input_seq": int(teacher_input_seq),
        "teacher_input_text": teacher_input_text,
        "class_finished": bool(class_finished),
        "final_pdf_token": final_pdf_token,
        "pointer_x_norm": px,
        "pointer_y_norm": py,
        "pointer_ts_ms": pts,
        "clarification_seq": int(clarif_seq),
        "clarification": clarif_text,
    }


def _validate_session_key_or_403(key: str) -> None:
    ok, msg = shared_presentation.validate_student_key(key)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)


def build_api() -> FastAPI:
    api = FastAPI()

    @api.exception_handler(KeyError)
    async def _ignore_gradio_queue_keyerror(request, exc: KeyError):
        return JSONResponse(
            status_code=410,
            content={"detail": "Evento expirado. Recarga la página si persiste."},
        )

    @api.get("/sync/state")
    def sync_state(key: str = Query(..., min_length=1)):
        _validate_session_key_or_403(key)
        return _build_sync_payload()

    @api.get("/sync/pdf")
    def sync_pdf(key: str = Query(..., min_length=1)):
        _validate_session_key_or_403(key)
        pdf_path, _, _, _ = shared_presentation.graph_pdf_context()
        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="No hay PDF compartido.")
        return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))

    @api.get("/sync/final_pdf")
    def sync_final_pdf(key: str = Query(..., min_length=1), token: Optional[str] = None):
        _validate_session_key_or_403(key)
        with shared_presentation.lock:
            final_pdf_path = shared_presentation.final_pdf_path
            expected_token = shared_presentation.final_pdf_token
        if not final_pdf_path or not os.path.exists(final_pdf_path):
            raise HTTPException(status_code=404, detail="No hay PDF final disponible.")
        if token and expected_token and token != expected_token:
            raise HTTPException(status_code=403, detail="Token de descarga no valido.")
        return FileResponse(
            final_pdf_path,
            media_type="application/pdf",
            filename=os.path.basename(final_pdf_path),
        )

    return api