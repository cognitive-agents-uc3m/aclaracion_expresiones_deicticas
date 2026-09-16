from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

from ....application.dto import GeneratedClarification
from ....application.ports.outbound.prompts import PromptRepositoryPort
from ....domain.errors import ClarificationGenerationFailed, ClarificationTimedOut
from ....domain.services.clarification_context_builder import ClarificationContext
from ....domain.services.slide_html_bboxes import annotate_html_with_bboxes
from ....domain.services.slide_layout import format_elements_inventory
from ....domain.value_objects.identifiers import SlideIdentifier
from ....domain.value_objects.slide_description import (
    DescriptionFormat,
    DescriptionStatus,
    SlideDescription,
)
from ....domain.value_objects.subject import Subject
from .base import ChatModel, ChatResponse, LlmUnavailable

logger = logging.getLogger(__name__)

_TRANSIENT = (
    "timeout",
    "timed out",
    "readtimeout",
    "connection",
    "temporarily unavailable",
    "service unavailable",
    "overloaded",
    "resource exhausted",
    "deadline exceeded",
    "429",
    "503",
)

def _is_transient(error: BaseException) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    return any(token in text for token in _TRANSIENT)

def _log_token_usage(operation: str, response: ChatResponse, **identifiers: object) -> None:
    input_tokens = response.input_tokens
    output_tokens = response.output_tokens
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    context = " ".join(f"{key}={value}" for key, value in identifiers.items())
    logger.info(
        "Tokens LLM | operacion=%s %s modelo=%s entrada=%s salida=%s total=%s",
        operation,
        context,
        response.model or "desconocido",
        input_tokens if input_tokens is not None else "n/d",
        output_tokens if output_tokens is not None else "n/d",
        total_tokens if total_tokens is not None else "n/d",
    )

class PromptedClarificationGenerator:

    name = "prompted"

    def __init__(
        self,
        *,
        chat: ChatModel,
        prompts: PromptRepositoryPort,
        timeout_seconds: float = 20.0,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.5,
        temperature: float = 0.0,
    ) -> None:
        self._chat = chat
        self._prompts = prompts
        self._timeout = timeout_seconds
        self._attempts = max(1, retry_attempts)
        self._backoff = max(0.0, retry_backoff_seconds)
        self._temperature = temperature

    def generate(self, context: ClarificationContext) -> GeneratedClarification:
        rendered = self._prompts.render(
            "clarification",
            subject=context.subject,
            variables=context.as_variables(),
        )

        started = time.monotonic()
        last_error: BaseException | None = None

        for attempt in range(1, self._attempts + 1):
            remaining = self._timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise ClarificationTimedOut(
                    f"Se agoto el presupuesto de {self._timeout:.1f}s antes del intento {attempt}."
                )
            try:
                response = self._chat.complete(
                    system=rendered.system,
                    user=rendered.user,
                    temperature=self._temperature,
                    timeout_seconds=remaining,
                )
                _log_token_usage(
                    "aclaracion",
                    response,
                    sesion=context.session_id.value,
                    diapositiva=context.slide_number,
                )
            except LlmUnavailable:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Fallo la generacion de aclaracion (intento %d/%d): %s: %s",
                    attempt,
                    self._attempts,
                    type(exc).__name__,
                    exc,
                )
                if not _is_transient(exc) or attempt >= self._attempts:
                    break
                time.sleep(min(self._backoff * attempt, max(0.0, remaining - 0.1)))
                continue

            if response.is_empty:
                last_error = ClarificationGenerationFailed("El proveedor devolvio texto vacio.")
                if attempt >= self._attempts:
                    break
                continue

            elapsed = time.monotonic() - started
            if elapsed > self._timeout:
                raise ClarificationTimedOut(
                    f"La generacion tardo {elapsed:.1f}s, por encima del presupuesto "
                    f"de {self._timeout:.1f}s."
                )

            return GeneratedClarification(
                text=response.text,
                model=response.model or self._chat.model_id,
                prompt_version=str(rendered.ref),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        if last_error is not None and _is_transient(last_error):
            raise ClarificationTimedOut(f"{type(last_error).__name__}: {last_error}")
        raise ClarificationGenerationFailed(
            f"No se pudo generar la aclaracion tras {self._attempts} intentos: {last_error}"
        )

class PromptedSlideDescriptionGenerator:

    name = "prompted"

    def __init__(
        self,
        *,
        vision: ChatModel,
        prompts: PromptRepositoryPort,
        fmt: DescriptionFormat = DescriptionFormat.TEXT,
        timeout_seconds: float = 180.0,
    ) -> None:
        self._vision = vision
        self._prompts = prompts
        self._fmt = fmt
        self._timeout = timeout_seconds

    def describe(
        self,
        *,
        slide: SlideIdentifier,
        slide_count: int,
        subject: Subject,
        image: bytes | None = None,
        pdf_page: bytes | None = None,
        layout: Mapping[str, Any] | None = None,
    ) -> SlideDescription:
        prompt_name = (
            "slide_description_html" if self._fmt is DescriptionFormat.HTML else "slide_description"
        )
        elements = _layout_elements(layout)
        rendered = self._prompts.render(
            prompt_name,
            subject=subject,
            variables={
                "SLIDE_NUMBER": str(slide.number),
                "SLIDE_COUNT": str(max(1, slide_count)),
                "ELEMENTS_INVENTORY": format_elements_inventory(elements),
            },
        )
        prompt_text = "\n\n".join(p for p in (rendered.system, rendered.user) if p)

        try:
            describe = getattr(self._vision, "describe", None)
            if callable(describe) and (image or pdf_page):
                response = describe(
                    prompt=prompt_text,
                    image=image,
                    pdf=pdf_page,
                    timeout_seconds=self._timeout,
                )
            else:
                response = self._vision.complete(
                    system=rendered.system, user=rendered.user, timeout_seconds=self._timeout
                )
            _log_token_usage(
                "descripcion_diapositiva",
                response,
                presentacion=slide.deck_id.value[:12],
                diapositiva=slide.number,
            )
        except Exception as exc:
            logger.warning("Fallo la descripcion de la diapositiva %s: %s", slide.number, exc)
            return SlideDescription(
                slide=slide,
                content="",
                status=DescriptionStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
                prompt_version=str(rendered.ref),
            )

        content = _strip_code_fence(response.text)
        if not content:
            return SlideDescription(
                slide=slide,
                content="",
                status=DescriptionStatus.FAILED,
                error="El modelo devolvio una descripcion vacia.",
                prompt_version=str(rendered.ref),
            )

        if self._fmt is DescriptionFormat.HTML and elements:
            content = annotate_html_with_bboxes(
                content,
                elements,
                page_width=_positive(layout, "page_w"),
                page_height=_positive(layout, "page_h"),
            )

        return SlideDescription(
            slide=slide,
            content=content,
            summary=_summarize(content),
            fmt=self._fmt,
            status=DescriptionStatus.READY,
            prompt_version=str(rendered.ref),
            model=response.model or self._vision.model_id,
        )

class PromptedNotesProcessor:

    name = "prompted"

    def __init__(
        self,
        *,
        chat: ChatModel,
        prompts: PromptRepositoryPort,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._chat = chat
        self._prompts = prompts
        self._timeout = timeout_seconds

    def process(self, raw_text: str, *, subject: Subject = Subject.GENERIC) -> str:
        cleaned = (raw_text or "").strip()
        if not cleaned:
            return ""
        rendered = self._prompts.render(
            "notes_processing", subject=subject, variables={"NOTES": cleaned}
        )
        response = self._chat.complete(
            system=rendered.system, user=rendered.user, timeout_seconds=self._timeout
        )

        return response.text.strip() or cleaned

class PassthroughNotesProcessor:

    name = "passthrough"

    def process(self, raw_text: str, *, subject: Subject = Subject.GENERIC) -> str:
        import re

        cleaned = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
        cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return re.sub(r"\n{4,}", "\n\n\n", cleaned).strip()

def _layout_elements(layout: Mapping[str, Any] | None) -> list[dict]:

    if isinstance(layout, Sequence) and not isinstance(layout, (str, bytes)):
        raw: Any = layout
    else:
        raw = (layout or {}).get("elements")
    return [element for element in (raw or []) if isinstance(element, Mapping)]

def _positive(layout: Mapping[str, Any] | None, key: str) -> float:
    if not isinstance(layout, Mapping):
        return 0.0
    try:
        return max(0.0, float(layout.get(key) or 0.0))
    except (TypeError, ValueError):
        return 0.0

def _strip_code_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```html"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()

def _summarize(content: str) -> str:
    import html as html_lib
    import re

    text = re.sub(r"<[^>]+>", " ", content)
    text = " ".join(html_lib.unescape(text).split())
    if not text:
        return "Sin resumen."
    first = text.split(".")[0].strip()
    return (first or text)[:240]
