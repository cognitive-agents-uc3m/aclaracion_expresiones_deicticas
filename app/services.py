
import logging
from typing import List, Optional, Tuple
import fitz
from assistant.settings import settings
from assistant.slide_knowledge import slide_knowledge_store, slide_precompute_service
from .shared import shared_presentation

logger = logging.getLogger(__name__)

def descripcion_diapositiva_actual() -> str:
    pdf_path, slide_index, slide_count, _ = shared_presentation.graph_pdf_context()
    if not pdf_path or slide_count <= 0:
        return "Sin PDF compartido."

    try:
        _, record = slide_knowledge_store.get_slide_by_pdf(pdf_path, int(slide_index))
    except Exception:
        record = None

    if isinstance(record, dict) and record.get("status") == "ready":
        detailed = (record.get("detailed_description") or "").strip()
        if detailed:
            return detailed
        summary = (record.get("summary") or "").strip()
        if summary:
            return f"[Resumen]\n{summary}"
        return "Descripcion precomputada vacia."

    status = (record.get("status") if isinstance(record, dict) else None) or "no_disponible"
    err = (record.get("error") if isinstance(record, dict) else None) or ""
    deck = slide_knowledge_store.deck_status_text(pdf_path)
    if err:
        err = f"\nError: {str(err).strip()[:300]}"
    return f"Descripcion no disponible (estado={status}).\n{deck}{err}".strip()


def resolve_pdf_for_precompute(pdf_subido: Optional[str]) -> Tuple[Optional[str], int]:
    pdf_path = (pdf_subido or "").strip() or None
    if pdf_path:
        _, _, slide_count, _ = shared_presentation.graph_pdf_context()
        if slide_count > 0:
            return pdf_path, slide_count
        try:
            with fitz.open(pdf_path) as doc:
                return pdf_path, doc.page_count
        except Exception:
            return None, 0
    current_pdf, _, current_count, _ = shared_presentation.graph_pdf_context()
    return current_pdf, current_count

def precompute_snapshot(pdf_subido: Optional[str]) -> Tuple[str, float]:
    pdf_path, _ = resolve_pdf_for_precompute(pdf_subido)
    status_text = slide_knowledge_store.deck_status_text(pdf_path)
    progress = slide_knowledge_store.deck_progress_percent(pdf_path)
    if slide_precompute_service.is_pdf_inflight(pdf_path):
        status_text = f"{status_text} Trabajo en curso."
    return status_text, progress

def prompt_profile_choices() -> List[Tuple[str, str]]:
    templates = settings.SLIDE_DESCRIPTION_PROMPT_TEMPLATES or {}
    known_labels = {
        "ESTADISTICA": "Estadística",
        "INGENIERIA_SOFTWARE": "Ingeniería del software",
    }
    choices: List[Tuple[str, str]] = [
        (known_labels.get(str(k), str(k)), str(k)) for k in templates.keys()
    ]
    choices.sort(key=lambda item: item[0].lower())
    return choices

def set_active_prompt_profile(profile: str) -> Tuple[bool, str]:
    profile_key = (profile or "").strip()
    templates = settings.SLIDE_DESCRIPTION_PROMPT_TEMPLATES or {}
    if profile_key not in templates:
        return False, profile_key
    settings.config["ACTIVE_SLIDE_PROMPT_PROFILE"] = profile_key
    return True, profile_key