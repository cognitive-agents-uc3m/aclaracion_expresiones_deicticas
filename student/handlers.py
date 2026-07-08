import logging
import re
import threading
import time
from typing import Optional
import gradio as gr
from assistant.slide_knowledge import slide_knowledge_store
from assistant.tools import hardware
from .session import LocalSessionRuntime, RemoteDeckSync, auto_session_key, ensure_runtime, ensure_sync

logger = logging.getLogger(__name__)

def conectar(sync_obj, runtime_obj, session_key):
    sync = ensure_sync(sync_obj)
    del runtime_obj
    rt = LocalSessionRuntime()
    key = (session_key or "").strip() or auto_session_key()
    msg = sync.configure(key) if key else "Hora fuera de rango. No se pudo asignar clave automática."

    (
        slide_text, preview, remote_status, _remote_precompute,
        pdf_path, _, _, _px, _py, _pts,
        final_status, notes_status, format_status,
    ) = sync.snapshot()
    local_precompute = slide_knowledge_store.deck_status_text(pdf_path)
    return (
        sync, rt, msg,
        slide_text, preview, remote_status, local_precompute,
        final_status, notes_status, format_status,
        "", "", "", "",
        gr.update(visible=False),
    )

def refrescar(sync_obj, runtime_obj, notes_text):
    sync = ensure_sync(sync_obj)
    rt = ensure_runtime(runtime_obj)
    ok, msg = sync.sync(force_pdf=False)
    updated_notes = sync.set_student_notes(notes_text or "", marker_idle_seconds=3.0)
    notes_out = updated_notes if updated_notes is not None else gr.update()

    (
        slide_text, preview, remote_status, _remote_precompute,
        pdf_path, _, _, _px, _py, _pts,
        final_status, notes_status, format_status,
    ) = sync.snapshot()
    local_precompute = slide_knowledge_store.deck_status_text(pdf_path)
    status = msg if ok else f"Sincronizacion: {msg}"

    sync.consume_teacher_text()
    clarification = sync.consume_clarification() if ok else None
    if clarification:
        with rt.lock:
            rt.current_state["generated_description"] = clarification
            rt.last_deictic_clarification = clarification
        threading.Thread(target=hardware.speak_text, args=(clarification,), daemon=True).start()
        return (
            sync, rt, status,
            slide_text, preview, remote_status, local_precompute,
            final_status, notes_status, format_status,
            "", gr.update(), clarification, notes_out,
            gr.update(visible=True),
            str(time.monotonic()),
        )

    return (
        sync, rt, status,
        slide_text, preview, remote_status, local_precompute,
        final_status, notes_status, format_status,
        "", gr.update(), gr.update(), notes_out,
        gr.update(),
        gr.update(),
    )

def enviar(runtime_obj, sync_obj, texto, audio):
    rt = ensure_runtime(runtime_obj)
    sync = ensure_sync(sync_obj)
    rt.process_input(texto, audio, sync)
    router, _status, desc, visual = rt.snapshot()
    if desc:
        hardware.play_notification_sound()
    return rt, router, desc if desc else "-", gr.update(visible=visual), ""

def escuchar(runtime_obj):
    rt = ensure_runtime(runtime_obj)
    text = rt.speak_description()
    return rt, text, gr.update(visible=True)

def anunciar_diapositiva(sync_obj, runtime_obj):
    sync = ensure_sync(sync_obj)
    rt = ensure_runtime(runtime_obj)
    _, _preview, _remote_status, _precompute, _pdf_path, idx, count, *_ = sync.snapshot()
    text = "No hay presentación cargada." if count <= 0 else f"Diapositiva {idx + 1} de {count}."
    hardware.speak_text(text)
    return sync, rt

def insertar_aclaracion(sync_obj, runtime_obj, notes_text):
    sync = ensure_sync(sync_obj)
    rt = ensure_runtime(runtime_obj)
    with rt.lock:
        clar = (rt.last_deictic_clarification or "").strip()
    if not clar:
        logger.debug("Aclaración: no hay aclaración deíctica reciente.")
        return sync, gr.update()

    clar_one_line = re.sub(r"\s+", " ", clar).strip()
    tag = f"[Aclaración: {clar_one_line}]"
    base = (notes_text or "").rstrip()
    if base.endswith(tag):
        return sync, gr.update()
    new_notes = f"{base}\n\n{tag}\n" if base else f"{tag}\n"
    sync.set_student_notes_raw(new_notes)
    logger.info("Aclaración copiada a notas.")
    return sync, new_notes

def actualizar_notas(sync_obj, notes_text):
    sync = ensure_sync(sync_obj)
    sync.set_student_notes(notes_text or "")
    return sync