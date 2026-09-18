from __future__ import annotations

from dataclasses import dataclass

from ...domain.entities.clarification import Clarification
from ...domain.errors import (
    ClarificationNotFound,
    ClarificationTimedOut,
    NoClarificationAvailable,
    SlideDescriptionUnavailable,
)
from ...domain.events import (
    ClarificationFailed,
    ClarificationListened,
    ClarificationReady,
)
from ...domain.services.clarification_context_builder import ClarificationContextBuilder
from ...domain.services.clarification_validator import ClarificationValidator
from ...domain.value_objects.identifiers import ClarificationId, SessionId
from ...domain.value_objects.subject import Subject
from ..dto import ClarificationView, SpeechOutput
from ..ports.outbound import (
    ClarificationGeneratorPort,
    ClarificationRepository,
    ClockPort,
    EventPublisherPort,
    Notification,
    NotificationChannel,
    NotificationLevel,
    NotificationPort,
    SessionRepository,
    SlideDescriptionRepository,
    TelemetryEvent,
    TelemetryPort,
    TextToSpeechPort,
)
from ..settings import ApplicationSettings
from ..views import clarification_view

@dataclass(slots=True)
class GenerateClarification:

    sessions: SessionRepository
    clarifications: ClarificationRepository
    descriptions: SlideDescriptionRepository
    generator: ClarificationGeneratorPort
    context_builder: ClarificationContextBuilder
    validator: ClarificationValidator
    clock: ClockPort
    events: EventPublisherPort
    telemetry: TelemetryPort
    settings: ApplicationSettings
    notifier: "NotifyClarification | None" = None

    def execute(self, clarification_id: ClarificationId) -> Clarification:
        clarification = self.clarifications.get(clarification_id)
        if clarification is None:
            raise ClarificationNotFound(f"No existe la aclaracion {clarification_id}.")

        session = self.sessions.get(clarification.session_id)
        subject = session.subject if session else Subject.GENERIC
        slide_count = session.slide_count if session else 0
        started = self.clock.monotonic()

        try:
            cache_started = self.clock.monotonic()
            description = self.descriptions.get(clarification.slide)
            self.telemetry.record_latency(
                "slide_description.cache_get",
                (self.clock.monotonic() - cache_started) * 1000.0,
                session_id=clarification.session_id.value,
                slide_number=clarification.slide.number,
                found=description is not None,
            )
            context = self.context_builder.rebuild(
                clarification=clarification,
                description=description,
                subject=subject,
                slide_count=slide_count,
                require_description=self.settings.clarification.require_description,
            )
        except SlideDescriptionUnavailable as exc:
            return self._fail(clarification, str(exc), timed_out=False)

        try:
            generated = self.generator.generate(context)
        except ClarificationTimedOut as exc:
            return self._fail(clarification, str(exc), timed_out=True)
        except Exception as exc:
            self.telemetry.record_error(
                "clarification.generate", exc, session_id=clarification.session_id.value
            )
            return self._fail(clarification, f"{type(exc).__name__}: {exc}", timed_out=False)

        elapsed_ms = (self.clock.monotonic() - started) * 1000.0
        if elapsed_ms > self.settings.clarification.timeout_seconds * 1000.0:
            return self._fail(
                clarification,
                f"la generacion tardo {elapsed_ms / 1000.0:.1f}s, por encima del presupuesto",
                timed_out=True,
            )

        validation = self.validator.validate(generated.text)
        if not validation.is_valid:
            return self._fail(clarification, validation.reason, timed_out=False)

        now = self.clock.now()
        total_latency_ms = (
            int((now - clarification.requested_at).total_seconds() * 1000)
            if clarification.requested_at is not None
            else int(elapsed_ms)
        )
        ready = clarification.succeed(
            validation.text,
            at=now,
            model=generated.model,
            prompt_ref=clarification.prompt_ref,
            latency_ms=int(elapsed_ms),
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
        )
        self.clarifications.save(ready)

        current_slide = session.current_slide if session else None
        is_stale = ready.is_stale_for(current_slide)

        if is_stale and self.settings.clarification.discard_when_stale:
            discarded = ready.discard("el profesor cambio de diapositiva", at=now)
            self.clarifications.save(discarded)
            self.telemetry.record(
                TelemetryEvent(
                    name="clarification.discarded_stale",
                    value=1.0,
                    attributes={"session_id": clarification.session_id.value},
                    occurred_at=now,
                )
            )
            return discarded

        if session is not None:
            with self.sessions.transaction(clarification.session_id) as live:
                live.remember_clarification(ready.clarification_id)

                live.retain_context(
                    self.settings.session.context_keep_after_clarification,
                    slide=live.current_slide,
                )

        self.telemetry.record(
            TelemetryEvent(
                name="clarification.generated",
                value=elapsed_ms,
                unit="ms",
                attributes={
                    "session_id": clarification.session_id.value,
                    "slide_number": ready.slide.number,
                    "model": ready.model,
                    "prompt_version": str(ready.prompt_ref) if ready.prompt_ref else "",
                    "input_tokens": generated.input_tokens,
                    "output_tokens": generated.output_tokens,
                    "total_latency_ms": total_latency_ms,
                    "truncated": validation.truncated,
                    "preface_removed": validation.preface_removed,
                    "stale": is_stale,
                },
                occurred_at=now,
            )
        )
        self.events.publish(
            ClarificationReady(
                occurred_at=now,
                session_id=ready.session_id,
                clarification_id=ready.clarification_id,
                slide=ready.slide,
                text=ready.text,
                is_stale=is_stale,
                latency_ms=int(elapsed_ms),
            )
        )
        self.telemetry.record_latency(
            "clarification.total",
            total_latency_ms,
            session_id=ready.session_id.value,
            slide_number=ready.slide.number,
            model=ready.model,
            stale=is_stale,
        )
        if self.notifier is not None:
            self.notifier.execute(ready, is_stale=is_stale)
        return ready

    def _fail(self, clarification: Clarification, error: str, *, timed_out: bool) -> Clarification:
        now = self.clock.now()
        failed = clarification.fail(error, at=now, timed_out=timed_out)
        self.clarifications.save(failed)
        self.events.publish(
            ClarificationFailed(
                occurred_at=now,
                session_id=failed.session_id,
                clarification_id=failed.clarification_id,
                slide=failed.slide,
                status=failed.status,
                error=error,
            )
        )
        self.telemetry.record(
            TelemetryEvent(
                name="clarification.failed",
                value=1.0,
                attributes={
                    "session_id": failed.session_id.value,
                    "status": failed.status.value,
                    "error": error[:200],
                },
                occurred_at=now,
            )
        )
        return failed

@dataclass(slots=True)
class NotifyClarification:

    notifications: NotificationPort
    settings: ApplicationSettings

    def execute(self, clarification: Clarification, *, is_stale: bool = False) -> None:
        if not clarification.is_available:
            return

        view = clarification_view(clarification)
        assert view is not None

        if self.settings.clarification.announce_availability:
            channels: list[NotificationChannel] = [NotificationChannel.LIVE_REGION]
            if self.settings.clarification.notification_sound and (
                self.settings.accessibility.sounds_enabled
            ):
                channels.append(NotificationChannel.SOUND)
            if self.settings.clarification.auto_play:
                channels.append(NotificationChannel.SPEECH)

            message = view.announcement if not is_stale else (
                f"Aclaracion disponible de la diapositiva {clarification.slide.number}. "
                "El profesor ya ha avanzado."
            )
            self.notifications.notify(
                Notification(
                    message=message,
                    level=NotificationLevel.INFO,
                    channels=tuple(channels),
                    politeness=self.settings.accessibility.clarification_politeness,
                    session_id=clarification.session_id,
                    payload={
                        "clarification_id": clarification.clarification_id.value,
                        "slide_number": clarification.slide.number,
                        "text": clarification.text if self.settings.clarification.auto_play else "",
                        "auto_play": self.settings.clarification.auto_play,
                    },
                )
            )

@dataclass(slots=True)
class GetLatestClarification:
    sessions: SessionRepository
    clarifications: ClarificationRepository

    def execute(self, session_id: SessionId) -> ClarificationView | None:
        session = self.sessions.get(session_id)
        latest = self.clarifications.latest_for_session(session_id)
        return clarification_view(
            latest, current_slide=session.current_slide if session else None
        )

@dataclass(slots=True)
class ListenClarification:

    sessions: SessionRepository
    clarifications: ClarificationRepository
    tts: TextToSpeechPort
    clock: ClockPort
    events: EventPublisherPort
    telemetry: TelemetryPort

    def execute(
        self, session_id: SessionId, *, clarification_id: ClarificationId | None = None
    ) -> SpeechOutput:
        clarification = (
            self.clarifications.get(clarification_id)
            if clarification_id is not None
            else self.clarifications.latest_for_session(session_id)
        )
        if clarification is None or not clarification.is_available:
            raise NoClarificationAvailable("Todavia no hay ninguna aclaracion disponible.")

        now = self.clock.now()
        self.clarifications.save(clarification.mark_listened())
        self.events.publish(
            ClarificationListened(
                occurred_at=now,
                session_id=session_id,
                clarification_id=clarification.clarification_id,
            )
        )
        self.telemetry.record(
            TelemetryEvent(
                name="clarification.listened",
                value=1.0,
                attributes={
                    "session_id": session_id.value,
                    "slide_number": clarification.slide.number,
                },
                occurred_at=now,
            )
        )
        return self.tts.synthesize(clarification.text)

__all__ = [
    "GenerateClarification",
    "GetLatestClarification",
    "ListenClarification",
    "NotifyClarification",
]
