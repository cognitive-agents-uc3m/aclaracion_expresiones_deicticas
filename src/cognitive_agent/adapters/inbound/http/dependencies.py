from __future__ import annotations

from fastapi import HTTPException, Request

from ....domain.errors import (
    ClarificationNotFound,
    DomainError,
    InvalidSlideIndex,
    NoActiveDeck,
    NoClarificationAvailable,
    PromptNotFound,
    SessionAlreadyEnded,
    SessionNotFound,
    SlideDescriptionUnavailable,
)
from ....domain.value_objects.identifiers import SessionId
from ....infrastructure.dependency_injection.container import Container

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    SessionNotFound: 404,
    ClarificationNotFound: 404,
    PromptNotFound: 500,
    NoClarificationAvailable: 409,
    SessionAlreadyEnded: 409,
    NoActiveDeck: 409,
    SlideDescriptionUnavailable: 409,
    InvalidSlideIndex: 400,
}

def status_for(error: DomainError) -> int:
    for error_type, status in STATUS_BY_ERROR.items():
        if isinstance(error, error_type):
            return status
    return 400

def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(status_code=503, detail="El servicio aun no esta listo.")
    return container

def session_id_of(raw: str) -> SessionId:
    clean = (raw or "").strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Falta el identificador de sesion.")
    return SessionId(clean)
