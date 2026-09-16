from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ....domain.errors import DomainError
from ....infrastructure.config.settings import Settings, load_settings
from ....infrastructure.dependency_injection.container import Container, build_container
from ....infrastructure.logging.setup import configure_logging
from .dependencies import status_for
from .events_router import router as events_router
from .health_router import router as health_router
from .student_router import router as student_router
from .teacher_router import router as teacher_router

logger = logging.getLogger(__name__)

def create_app(
    *, settings: Settings | None = None, container: Container | None = None
) -> FastAPI:
    resolved_settings = settings or (container.settings if container else load_settings())
    configure_logging(
        level=resolved_settings.logging.level, fmt=resolved_settings.logging.format
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container or build_container(resolved_settings)
        problems = app.state.container.settings.validate()
        if problems:
            logger.warning("La configuracion tiene %d problemas; ver /readyz.", len(problems))
        logger.info(
            "Cognitive Agent listo | entorno=%s llm=%s stt=%s persistencia=%s",
            resolved_settings.environment,
            resolved_settings.llm.provider,
            resolved_settings.stt.provider,
            resolved_settings.persistence.backend,
        )
        try:
            yield
        finally:
            app.state.container.shutdown()
            logger.info("Cognitive Agent detenido limpiamente.")

    app = FastAPI(
        title="Cognitive Agent",
        version=__import__("cognitive_agent").__version__,
        description=(
            "Asistente accesible de aula: resuelve en tiempo real las expresiones "
            "deicticas del profesorado para alumnado ciego."
        ),
        lifespan=lifespan,
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError) -> JSONResponse:

        return JSONResponse(
            status_code=status_for(exc),
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    app.include_router(health_router)
    app.include_router(teacher_router)
    app.include_router(student_router)
    app.include_router(events_router)

    _mount_web_client(app)
    return app

def _mount_web_client(app: FastAPI) -> None:

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if not web_dir.is_dir():
        return

    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(web_dir / "index.html")

def get_asgi_app() -> FastAPI:
    return create_app()
