from __future__ import annotations

import json
import logging
import re
from ....domain.services.deictic_detection_service import DeicticDetectionService
from ....domain.value_objects.deictic import DeicticDetection, DeicticExpression, DeicticKind
from ....domain.value_objects.subject import Subject
from .base import ChatModel, ChatResponse

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

def _log_token_usage(response: ChatResponse, *, subject: Subject) -> None:
    input_tokens = response.input_tokens
    output_tokens = response.output_tokens
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    logger.info(
        "Tokens LLM | operacion=chequeo_deixis asignatura=%s modelo=%s "
        "entrada=%s salida=%s total=%s",
        subject.value,
        response.model or "desconocido",
        input_tokens if input_tokens is not None else "n/d",
        output_tokens if output_tokens is not None else "n/d",
        total_tokens if total_tokens is not None else "n/d",
    )

class RuleBasedDeicticDetector:
    name = "rules"

    def __init__(self, service: DeicticDetectionService | None = None) -> None:
        self._service = service or DeicticDetectionService()

    def detect(self, text: str, *, subject: Subject = Subject.GENERIC) -> DeicticDetection:
        return self._service.detect(text)

class LlmDeicticDetector:
    name = "llm"

    def __init__(
        self,
        *,
        chat: ChatModel,
        prompts,
        timeout_seconds: float = 8.0,
        fallback: RuleBasedDeicticDetector | None = None,
    ) -> None:
        self._chat = chat
        self._prompts = prompts
        self._timeout = timeout_seconds
        self._fallback = fallback or RuleBasedDeicticDetector()

    def detect(self, text: str, *, subject: Subject = Subject.GENERIC) -> DeicticDetection:
        clean = (text or "").strip()
        if not clean:
            return DeicticDetection.none("fragmento vacio", detector=self.name)

        rendered = self._prompts.render("deictic_detection", subject=subject)
        instruction = (
            f"{rendered.system}\n\n"
            "Responde SOLO con JSON: "
            '{"lanzar": true|false, "expresion": "...", "motivo": "..."}'
        )

        try:
            response = self._chat.complete(
                system=instruction, user=clean, timeout_seconds=self._timeout
            )
            _log_token_usage(response, subject=subject)
        except Exception as exc:

            logger.warning("El detector por LLM fallo (%s); se usan reglas.", exc)
            return self._fallback.detect(clean, subject=subject)

        payload = _parse_json(response.text)
        if payload is None:
            return self._fallback.detect(clean, subject=subject)

        if not payload.get("lanzar"):
            return DeicticDetection.none(
                str(payload.get("motivo", "el modelo no vio referencia visual")),
                detector=self.name,
            )

        surface = str(payload.get("expresion") or "").strip()
        start = clean.lower().find(surface.lower()) if surface else -1
        if start < 0:
            start = 0
            surface = surface or clean[:24]

        return DeicticDetection(
            expressions=(
                DeicticExpression(
                    surface=surface,
                    kind=DeicticKind.DEMONSTRATIVE,
                    start=start,
                    end=start + len(surface),
                    confidence=0.8,
                ),
            ),
            detector=self.name,
        )

class RulesThenLlmDeicticDetector:
    name = "rules_then_llm"

    def __init__(
        self,
        *,
        rules: RuleBasedDeicticDetector,
        llm: LlmDeicticDetector,
    ) -> None:
        self._rules = rules
        self._llm = llm

    def detect(self, text: str, *, subject: Subject = Subject.GENERIC) -> DeicticDetection:
        detection = self._rules.detect(text, subject=subject)
        if not detection.detected:
            return detection

        refined = self._llm.detect(text, subject=subject)
        if refined.detected:
            return DeicticDetection(
                expressions=detection.expressions, detector=self.name
            )
        return DeicticDetection.none(refined.suppressed_by, detector=self.name)

def _parse_json(text: str) -> dict | None:
    match = _JSON_BLOCK.search(text or "")
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None
