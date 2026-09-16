from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from ...domain.entities.clarification import Clarification
from ...domain.errors import SessionNotFound
from ...domain.events import (
    ClarificationRequested,
    DeicticExpressionDetected,
    DeicticExpressionDismissed,
    TranscriptFragmentReceived,
)
from ...domain.value_objects.identifiers import SessionId
from ...domain.value_objects.subject import Subject
from ...domain.value_objects.transcript import TranscriptFragment, normalize_text
from ..dto import ProcessFragmentResult, TranscriptFragmentCommand
from ..ports.outbound import (
    ClarificationRepository,
    ClockPort,
    DeicticDetectionLogPort,
    DeicticDetectorPort,
    EventPublisherPort,
    PromptRepositoryPort,
    SessionRepository,
    SpeechToTextPort,
    TaskSchedulerPort,
    TelemetryEvent,
    TelemetryPort,
)
from ..settings import ApplicationSettings

logger = logging.getLogger(__name__)

class ClarificationDebouncer:

    def __init__(self, *, min_interval_seconds: float) -> None:
        self._min_interval = max(0.0, min_interval_seconds)
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_generate(self, session_id: SessionId, *, monotonic_now: float) -> bool:
        if self._min_interval <= 0:
            return True
        key = session_id.value
        with self._lock:
            previous = self._last.get(key)
            if previous is not None and (monotonic_now - previous) < self._min_interval:
                return False
            self._last[key] = monotonic_now
            return True

    def forget(self, session_id: SessionId) -> None:
        with self._lock:
            self._last.pop(session_id.value, None)

@dataclass(slots=True)
class DetectDeicticExpression:

    detector: DeicticDetectorPort
    clock: ClockPort
    telemetry: TelemetryPort

    def execute(self, text: str, *, subject: Subject = Subject.GENERIC):
        started = self.clock.monotonic()
        detection = self.detector.detect(normalize_text(text), subject=subject)
        elapsed_ms = (self.clock.monotonic() - started) * 1000.0
        self.telemetry.record_latency(
            "deixis.detection",
            elapsed_ms,
            detector=detection.detector,
            detected=detection.detected,
            probability=detection.decision_probability,
            threshold=detection.decision_threshold,
        )
        return detection

@dataclass(slots=True)
class ProcessTranscriptFragment:
    sessions: SessionRepository
    clarifications: ClarificationRepository
    detector: DeicticDetectorPort
    stt: SpeechToTextPort | None
    clock: ClockPort
    events: EventPublisherPort
    scheduler: TaskSchedulerPort
    telemetry: TelemetryPort
    prompts: PromptRepositoryPort
    settings: ApplicationSettings
    deictic_log: DeicticDetectionLogPort | None = None
    pointer_resolver: object = None

    generate_callback: object = None

    debouncer: ClarificationDebouncer = field(
        default_factory=lambda: ClarificationDebouncer(min_interval_seconds=3.0)
    )

    def execute(self, command: TranscriptFragmentCommand) -> ProcessFragmentResult:
        if not command.has_payload:
            return ProcessFragmentResult(accepted=False, reason="fragmento vacio")

        text = self._resolve_text(command)
        if not text:
            return ProcessFragmentResult(accepted=False, reason="sin voz legible")

        now = command.received_at or self.clock.now()

        with self.sessions.transaction(command.session_id) as session:
            fragment = session.observe_fragment(
                TranscriptFragment(
                    text=text, received_at=now, session_id=command.session_id
                )
            )
            subject = session.subject
            slide_count = session.slide_count
            recent_context = session.context.preceding_text()

            puntero = session.fresh_pointer(now=now)
            document_path = session.deck.source_name if session.deck else ""

        self.events.publish(
            TranscriptFragmentReceived(
                occurred_at=now,
                session_id=command.session_id,
                text=text,
                slide=fragment.slide,
            )
        )

        detection_started = self.clock.monotonic()
        detection = self.detector.detect(text, subject=subject)
        self.telemetry.record_latency(
            "deixis.detection",
            (self.clock.monotonic() - detection_started) * 1000.0,
            detector=detection.detector,
            detected=detection.detected,
            session_id=command.session_id.value,
            probability=detection.decision_probability,
            threshold=detection.decision_threshold,
        )

        if not detection.detected:
            self.events.publish(
                DeicticExpressionDismissed(
                    occurred_at=now,
                    session_id=command.session_id,
                    text=text,
                    reason=detection.suppressed_by or "sin expresiones deicticas",
                )
            )
            return ProcessFragmentResult(
                accepted=True,
                text=text,
                detected=False,
                reason=detection.suppressed_by or "",
                slide_number=fragment.slide.number if fragment.slide else None,
            )

        expression = detection.primary
        self.events.publish(
            DeicticExpressionDetected(
                occurred_at=now,
                session_id=command.session_id,
                expression=expression,
                slide=fragment.slide,
                detector=detection.detector,
            )
        )
        if self.deictic_log is not None and expression is not None:
            self.deictic_log.record_detection(
                session_id=command.session_id,
                occurred_at=now,
                slide_number=fragment.slide.number if fragment.slide else None,
                expression_surface=expression.surface,
                expression_kind=expression.kind.value,
            )
        self.telemetry.record(
            TelemetryEvent(
                name="deixis.detected",
                value=1.0,
                attributes={
                    "session_id": command.session_id.value,
                    "kind": expression.kind.value if expression else "",
                    "confidence": round(detection.max_confidence, 3),
                    "slide_number": fragment.slide.number if fragment.slide else None,
                },
                occurred_at=now,
            )
        )

        if fragment.slide is None or slide_count == 0:
            return ProcessFragmentResult(
                accepted=True,
                text=text,
                detected=True,
                expression=expression.surface if expression else "",
                reason="no hay presentacion activa a la que referirse",
            )

        if not self.debouncer.should_generate(
            command.session_id, monotonic_now=self.clock.monotonic()
        ):
            return ProcessFragmentResult(
                accepted=True,
                text=text,
                detected=True,
                expression=expression.surface if expression else "",
                reason="agrupada con la aclaracion anterior",
                slide_number=fragment.slide.number,
            )

        pointed_element = self._resolve_pointer(puntero, document_path)
        clarification = Clarification.requested(
            session_id=command.session_id,
            slide=fragment.slide,
            trigger_fragment=text,
            description_used="",
            recent_context=recent_context,
            pointed_element=pointed_element,
            trigger_expression=expression,
            at=now,
            prompt_ref=self.prompts.ref("clarification", subject=subject),
        )
        self.clarifications.save(clarification)
        self.events.publish(
            ClarificationRequested(
                occurred_at=now,
                session_id=command.session_id,
                clarification_id=clarification.clarification_id,
                slide=fragment.slide,
                pointed_element=pointed_element,
            )
        )

        if self.generate_callback is not None:
            self.scheduler.submit(
                self.generate_callback.execute,
                clarification.clarification_id,
            )

        return ProcessFragmentResult(
            accepted=True,
            text=text,
            detected=True,
            expression=expression.surface if expression else "",
            clarification_id=clarification.clarification_id.value,
            slide_number=fragment.slide.number,
        )

    def _resolve_pointer(self, puntero, document_path: str) -> str:

        if puntero is None or self.pointer_resolver is None:
            return ""
        try:
            return self.pointer_resolver.describe_point(
                document_path=document_path,
                slide_index=puntero.slide.index,
                x=puntero.x,
                y=puntero.y,
                deck_id=puntero.slide.deck_id.value,
            )
        except Exception:
            logger.debug("No se pudo resolver el elemento senalado.", exc_info=True)
            return ""

    def _resolve_text(self, command: TranscriptFragmentCommand) -> str:
        text = normalize_text(command.text)
        if text:
            return text
        if command.audio is None or self.stt is None:
            return ""

        session = self.sessions.get(command.session_id)
        if session is None:
            raise SessionNotFound(f"No existe la sesion {command.session_id}.")

        started = self.clock.monotonic()
        result = self.stt.transcribe(command.audio, context_hint=session.context.as_text())
        elapsed_ms = (self.clock.monotonic() - started) * 1000.0
        self.telemetry.record_latency(
            "stt.transcribe",
            elapsed_ms,
            provider=result.provider or self.stt.name,
            model=result.model,
            session_id=command.session_id.value,
        )
        return normalize_text(result.text)

__all__ = [
    "ClarificationDebouncer",
    "DetectDeicticExpression",
    "ProcessTranscriptFragment",
]
