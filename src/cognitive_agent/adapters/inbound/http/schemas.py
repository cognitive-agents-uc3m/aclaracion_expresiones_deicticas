from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from ....application.dto import (
    ClarificationView,
    NotesView,
    ProcessFragmentResult,
    SessionView,
    SlideView,
)

class StartSessionBody(BaseModel):
    subject: str = Field(default="generic", description="generic | statistics | software_engineering")
    title: str = ""
    access_key: str = Field(default="", description="Clave con la que el alumno se une.")

class RenameSessionBody(BaseModel):
    title: str = ""

class LoadDeckBody(BaseModel):
    deck_id: str
    slide_count: int = Field(ge=0)
    title: str = ""
    source_name: str = ""

class ChangeSlideBody(BaseModel):
    index: int | None = None
    delta: int | None = None

class TranscriptBody(BaseModel):
    text: str = ""

class NotesBody(BaseModel):
    text: str = ""
    is_keystroke: bool = True

class InsertClarificationBody(BaseModel):
    clarification_id: str | None = None

class JumpBody(BaseModel):
    slide_index: int | None = None

def slide_payload(view: SlideView) -> dict[str, Any]:
    return {
        "index": view.index,
        "number": view.number,
        "count": view.count,
        "label": view.label,
        "has_description": view.has_description,
        "description_ready": view.description_ready,
        "description": view.description,
        "description_format": view.description_format,
    }

def clarification_payload(view: ClarificationView | None) -> dict[str, Any] | None:
    if view is None:
        return None
    return {
        "id": view.clarification_id,
        "text": view.text,
        "slide_number": view.slide_number,
        "slide_index": view.slide_index,
        "status": view.status,
        "is_stale": view.is_stale,
        "listened": view.listened,
        "inserted": view.inserted,
        "available": view.is_available,
        "announcement": view.announcement,
        "created_at": view.created_at.isoformat() if view.created_at else None,
        "model": view.model,
        "prompt_version": view.prompt_version,
        "latency_ms": view.latency_ms,
        "trigger_expression": view.trigger_expression,
    }

def notes_payload(view: NotesView) -> dict[str, Any]:
    return {
        "text": view.text,
        "entry_count": view.entry_count,
        "current_slide_number": view.current_slide_number,
        "outline": [
            {"sequence": seq, "kind": kind, "label": label} for seq, kind, label in view.outline
        ],
        "caret_offset": view.caret_offset,
        "restored_markers": list(view.restored_markers),
        "inserted_markers": list(view.inserted_markers),
        "announcement": view.announcement,
    }

def session_payload(view: SessionView) -> dict[str, Any]:
    return {
        "session_id": view.session_id,
        "subject": view.subject,
        "title": view.title,
        "is_active": view.is_active,
        "slide": slide_payload(view.slide),
        "started_at": view.started_at.isoformat() if view.started_at else None,
        "ended_at": view.ended_at.isoformat() if view.ended_at else None,
        "latest_clarification": clarification_payload(view.latest_clarification),
    }

def fragment_payload(result: ProcessFragmentResult) -> dict[str, Any]:
    return {
        "accepted": result.accepted,
        "text": result.text,
        "detected": result.detected,
        "expression": result.expression,
        "clarification_id": result.clarification_id,
        "reason": result.reason,
        "slide_number": result.slide_number,
    }
