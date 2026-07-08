import io
import json
import logging
import os
import shutil
import tempfile
import uuid
import wave
from typing import Dict, Optional, Tuple
import numpy as np
from fastapi import APIRouter, Cookie, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from assistant.settings import settings
from assistant.slide_knowledge import slide_precompute_service
from assistant.tools import hardware
from .services import (
    descripcion_diapositiva_actual,
    precompute_snapshot,
    prompt_profile_choices,
    set_active_prompt_profile,
)
from .session import SessionRuntime
from .shared import shared_presentation, shared_teacher_input

logger = logging.getLogger(__name__)

_sessions: Dict[str, SessionRuntime] = {}

_fallback_sid: Optional[str] = None

def create_session() -> str:
    sid = str(uuid.uuid4())
    _sessions[sid] = SessionRuntime()
    return sid

def install_fallback_session() -> str:
    global _fallback_sid
    _fallback_sid = create_session()
    return _fallback_sid

def _get_rt(sid: Optional[str]) -> Optional[SessionRuntime]:
    effective = sid or _fallback_sid
    if not effective:
        return None
    return _sessions.get(effective)

def _require_rt(sid: Optional[str]) -> SessionRuntime:
    rt = _get_rt(sid)
    if rt is None:
        raise HTTPException(status_code=401, detail="Sesion no valida. Inicia sesion de nuevo.")
    return rt

def _slide_nav_payload(pdf_path: Optional[str] = None) -> dict:
    slide_text, _, shared_status = shared_presentation.snapshot()
    precompute_status, precompute_progress = precompute_snapshot(pdf_path)
    return {
        "slide_label": slide_text,
        "shared_status": shared_status,
        "precompute_status": precompute_status,
        "precompute_progress": precompute_progress,
    }

def _assistant_payload(rt: SessionRuntime) -> dict:
    _, es_visual, status = rt.snapshot()
    _, _, shared_status = shared_presentation.snapshot()
    with rt.lock:
        desc = rt.current_state.get("generated_description") or ""
    return {
        "status": status,
        "shared_status": shared_status,
        "description": desc,
        "visual": es_visual,
        "tts_payload": rt.consume_tts_payload(),
    }

def _parse_wav(content: bytes) -> Tuple[int, np.ndarray]:
    with wave.open(io.BytesIO(content), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sample_width != 2:
        raise ValueError(f"Se esperaba PCM de 16 bits, llego sampwidth={sample_width}.")
    samples = np.frombuffer(frames, dtype=np.int16)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1).astype(np.int16)
    return int(sample_rate), samples

def build_web_routes() -> APIRouter:
    router = APIRouter()

    @router.post("/ui/login/teacher")
    async def login_teacher(response: Response, key: str = Form(...)):
        msg = shared_presentation.set_session_key(key)
        if msg != "Sesion de profesor iniciada.":
            raise HTTPException(status_code=403, detail=msg)
        sid = create_session()
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
        response.set_cookie("role", "teacher", httponly=False, samesite="lax")
        return {"ok": True, "session_key": (key or "").strip()}

    @router.post("/ui/login/student")
    async def login_student(response: Response, key: str = Form(...)):
        ok, msg = shared_presentation.validate_student_key(key)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)
        sid = create_session()
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
        response.set_cookie("role", "student", httponly=False, samesite="lax")
        response.set_cookie("student_key", (key or "").strip(), httponly=False, samesite="lax")
        return {"ok": True}

    @router.post("/ui/logout")
    async def logout(response: Response, sid: Optional[str] = Cookie(default=None)):
        if sid and sid in _sessions:
            del _sessions[sid]
        response.delete_cookie("sid")
        response.delete_cookie("role")
        response.delete_cookie("student_key")
        return {"ok": True}

    @router.post("/ui/teacher/pdf")
    def upload_pdf(
        file: UploadFile = File(...),
        sid: Optional[str] = Cookie(default=None),
    ):
        _require_rt(sid)
        content = file.file.read()
        suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(content)
        tmp.close()
        shared_presentation.set_pdf(tmp.name)
        return {"ok": True, **_slide_nav_payload(tmp.name)}

    @router.post("/ui/teacher/slides/prev")
    def slide_prev(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        shared_presentation.move_slide(-1)
        return _slide_nav_payload()

    @router.post("/ui/teacher/slides/next")
    def slide_next(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        shared_presentation.move_slide(1)
        return _slide_nav_payload()

    @router.get("/ui/teacher/slides/image")
    def teacher_slide_image(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        _, preview_path, _ = shared_presentation.snapshot()
        if not preview_path or not os.path.exists(preview_path):
            raise HTTPException(status_code=404, detail="No hay imagen de diapositiva.")
        return FileResponse(preview_path, media_type="image/png")


    @router.get("/ui/student/slides/image")
    def student_slide_image(key: str):
        ok, msg = shared_presentation.validate_student_key(key)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)
        _, preview_path, _ = shared_presentation.snapshot()
        if not preview_path or not os.path.exists(preview_path):
            raise HTTPException(status_code=404, detail="No hay imagen disponible.")
        return FileResponse(preview_path, media_type="image/png")

    @router.post("/ui/teacher/send")
    def teacher_send(
        text: str = Form(...),
        sid: Optional[str] = Cookie(default=None),
    ):
        rt = _require_rt(sid)
        published = rt.process_manual_input(text.strip(), None, None, None)
        if published:
            shared_teacher_input.publish(published)
        return _assistant_payload(rt)

    @router.post("/ui/teacher/audio")
    def teacher_audio(
        file: UploadFile = File(...),
        sid: Optional[str] = Cookie(default=None),
    ):
        rt = _require_rt(sid)
        content = file.file.read()
        if not content:
            return {"ok": False, "transcribed": ""}

        ext = ".webm"
        ct = (file.content_type or "").lower()
        if "ogg" in ct:
            ext = ".ogg"
        elif "wav" in ct:
            ext = ".wav"
        elif "mp4" in ct or "mpeg" in ct:
            ext = ".mp4"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.write(content)
        tmp.close()

        try:
            with rt.lock:
                context_hint = rt.current_state.get("current_context_text", "")
            text = hardware.transcribe_audio_file(tmp.name, prompt_text=context_hint)
        except Exception as ex:
            logger.warning("Error transcribiendo audio: %s", ex)
            text = ""
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        error = None
        if not text.strip() and ext != ".wav" and shutil.which("ffmpeg") is None:
            error = (
                "No se pudo transcribir: ffmpeg no esta instalado o no esta en el PATH "
                "(es necesario para decodificar el audio del navegador)."
            )
            logger.error(error)

        if text.strip():
            published = rt.process_manual_input(text.strip(), None, None, None)
            if published:
                shared_teacher_input.publish(published)

        payload = {"ok": not error, "transcribed": text.strip(), **_assistant_payload(rt)}
        if error:
            payload["error"] = error
        return payload

    @router.post("/ui/teacher/audio/stream")
    def teacher_audio_stream(
        file: UploadFile = File(...),
        sid: Optional[str] = Cookie(default=None),
    ):
        rt = _require_rt(sid)
        content = file.file.read()
        if not content:
            return {"ok": False, "detail": "Audio vacio."}
        try:
            sample_rate, samples = _parse_wav(content)
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"WAV no valido: {ex}")
        ok, detail = rt.enqueue_audio_segment(sample_rate, samples)
        return {"ok": ok, "detail": detail}

    @router.get("/ui/config/audio")
    async def audio_config():
        return {
            "vad_energy_threshold": settings.vad_energy_threshold,
            "vad_preroll_seconds": settings.vad_preroll_seconds,
            "vad_silence_seconds": settings.vad_silence_seconds,
            "vad_min_speech_seconds": settings.vad_min_speech_seconds,
            "vad_max_segment_seconds": settings.vad_max_segment_seconds,
        }

    @router.post("/ui/teacher/auto/start")
    async def teacher_auto_start(sid: Optional[str] = Cookie(default=None)):
        rt = _require_rt(sid)
        rt.set_auto_mode(True)
        _, _, status = rt.snapshot()
        return {"ok": True, "status": status}

    @router.post("/ui/teacher/auto/stop")
    async def teacher_auto_stop(sid: Optional[str] = Cookie(default=None)):
        rt = _require_rt(sid)
        rt.set_auto_mode(False)
        _, _, status = rt.snapshot()
        return {"ok": True, "status": status}

    @router.post("/ui/teacher/pointer")
    async def teacher_pointer(
        request: Request,
        sid: Optional[str] = Cookie(default=None),
    ):
        _require_rt(sid)
        body = await request.json()
        shared_presentation.update_pointer_from_payload(json.dumps(body))
        return {"ok": True}


    @router.post("/ui/teacher/precompute")
    def teacher_precompute(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        pdf_path, _, slide_count, _ = shared_presentation.graph_pdf_context()
        if not pdf_path or slide_count <= 0:
            return {"ok": False, "status": "No hay PDF valido para preprocesar.", "progress": 0}
        slide_precompute_service.enqueue_pdf(pdf_path, slide_count, mode="all")
        status, progress = precompute_snapshot(pdf_path)
        return {"ok": True, "status": status, "progress": progress}

    @router.post("/ui/teacher/precompute/retry")
    def teacher_precompute_retry(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        pdf_path, _, slide_count, _ = shared_presentation.graph_pdf_context()
        if not pdf_path or slide_count <= 0:
            return {"ok": False, "status": "No hay PDF para reintentar.", "progress": 0}
        slide_precompute_service.enqueue_retry_errors(pdf_path, slide_count)
        status, progress = precompute_snapshot(pdf_path)
        return {"ok": True, "status": status, "progress": progress}


    @router.post("/ui/teacher/finish")
    def teacher_finish(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        ok, msg = shared_presentation.finalize_class()
        return {"ok": ok, "status": msg}

    @router.post("/ui/teacher/prompt-profile")
    async def teacher_prompt_profile(
        profile: str = Form(...),
        sid: Optional[str] = Cookie(default=None),
    ):
        _require_rt(sid)
        ok, profile_key = set_active_prompt_profile(profile)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Perfil no valido: {profile_key}")
        return {"ok": True, "profile": profile_key}


    @router.get("/ui/teacher/state")
    def teacher_state(sid: Optional[str] = Cookie(default=None)):
        rt = _require_rt(sid)
        _, es_visual, status = rt.snapshot()
        slide_text, _, shared_status = shared_presentation.snapshot()
        precompute_status, precompute_progress = precompute_snapshot(None)
        desc = descripcion_diapositiva_actual()
        tts = rt.consume_tts_payload()
        with rt.lock:
            last_chunk = (rt.last_transcribed_chunk or "").strip()
            auto_mode = rt.auto_mode
            agent_desc = rt.current_state.get("generated_description") or ""
        with shared_presentation.lock:
            class_finished = shared_presentation.class_finished
        return {
            "status": status,
            "shared_status": shared_status,
            "slide_label": slide_text,
            "description": desc,
            "agent_response": agent_desc,
            "visual": es_visual,
            "tts_payload": tts,
            "precompute_status": precompute_status,
            "precompute_progress": precompute_progress,
            "last_transcribed": last_chunk,
            "auto_mode": auto_mode,
            "class_finished": class_finished,
        }

    @router.get("/ui/student/state")
    def student_state(key: str):
        ok, msg = shared_presentation.validate_student_key(key)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)
        slide_text, _, shared_status = shared_presentation.snapshot()
        desc = descripcion_diapositiva_actual()
        clarif_seq, clarif_text = shared_presentation.clarification_snapshot()
        with shared_presentation.lock:
            class_finished = shared_presentation.class_finished
            final_token = shared_presentation.final_pdf_token if class_finished else None
        return {
            "slide_label": slide_text,
            "description": desc,
            "shared_status": shared_status,
            "class_finished": class_finished,
            "final_pdf_token": final_token,
            "clarification": clarif_text,
            "clarification_seq": clarif_seq,
        }

    @router.get("/ui/prompts")
    async def get_prompt_profiles(sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        choices = prompt_profile_choices()
        return {
            "profiles": [{"label": lbl, "value": val} for lbl, val in choices],
            "active": settings.ACTIVE_SLIDE_PROMPT_PROFILE,
        }

    @router.get("/ui/prompt-text")
    async def get_prompt_text(profile: str, sid: Optional[str] = Cookie(default=None)):
        _require_rt(sid)
        templates = settings.SLIDE_DESCRIPTION_PROMPT_TEMPLATES or {}
        text = templates.get(profile)
        if text is None:
            raise HTTPException(status_code=404, detail=f"Perfil no encontrado: {profile}")
        return {"profile": profile, "text": str(text)}

    return router