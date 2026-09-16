from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ...domain.value_objects.identifiers import DeckId, SessionId, SlideIdentifier
from ...domain.value_objects.slide_description import DescriptionStatus, SlideDescription
from ...domain.value_objects.subject import Subject
from ..ports.outbound import (
    ClockPort,
    SlideDescriptionGeneratorPort,
    SlideDescriptionRepository,
    TaskSchedulerPort,
    TelemetryEvent,
    TelemetryPort,
)

logger = logging.getLogger(__name__)

class SlideContentSource(Protocol):

    def slide_image_bytes(self, path: str, index: int) -> bytes: ...

    def slide_pdf_bytes(self, path: str, index: int) -> bytes: ...

    def slide_layout(self, path: str, index: int) -> Mapping[str, Any]:

        ...

@dataclass(frozen=True, slots=True)
class PrecomputePolicy:

    inter_slide_delay_seconds: float = 1.0
    cooldown_every_n_slides: int = 5
    cooldown_seconds: float = 5.0
    retry_attempts: int = 2
    use_pdf_page: bool = True

@dataclass(slots=True)
class PrecomputeProgress:
    deck_id: str
    total: int
    ready: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(((self.ready + self.failed) / self.total) * 100.0, 1)

    @property
    def is_complete(self) -> bool:
        return self.total > 0 and (self.ready + self.failed) >= self.total

    def as_text(self) -> str:
        return (
            f"Preproceso: {self.percent:.1f}% | listas {self.ready}/{self.total}, "
            f"pendientes {self.pending}, con error {self.failed}."
        )

@dataclass(slots=True)
class PrecomputeDeck:
    descriptions: SlideDescriptionRepository
    generator: SlideDescriptionGeneratorPort
    documents: SlideContentSource
    scheduler: TaskSchedulerPort
    clock: ClockPort
    telemetry: TelemetryPort
    policy: PrecomputePolicy = field(default_factory=PrecomputePolicy)
    _inflight: set[str] = field(default_factory=set)

    def enqueue(
        self,
        *,
        deck_id: str,
        slide_count: int,
        document_path: str,
        subject: Subject,
        only_failed: bool = False,
    ) -> PrecomputeProgress:

        if deck_id in self._inflight:
            return self.progress(deck_id, slide_count)

        self._inflight.add(deck_id)
        self.scheduler.submit(
            self._run,
            deck_id,
            slide_count,
            document_path,
            subject,
            only_failed,
        )
        return self.progress(deck_id, slide_count)

    def progress(self, deck_id: str, slide_count: int = 0) -> PrecomputeProgress:
        ready, total, failed, _processing = self.descriptions.deck_progress(deck_id)
        total = total or slide_count
        return PrecomputeProgress(
            deck_id=deck_id,
            total=total,
            ready=ready,
            failed=failed,
            pending=max(0, total - ready - failed),
        )

    def describe_slide(
        self,
        *,
        deck_id: str,
        index: int,
        slide_count: int,
        document_path: str,
        subject: Subject,
    ) -> SlideDescription:

        slide = SlideIdentifier(DeckId(deck_id), index)
        started = self.clock.monotonic()

        image = pdf_page = None
        try:
            if self.policy.use_pdf_page:
                pdf_page = self.documents.slide_pdf_bytes(document_path, index)
            else:
                image = self.documents.slide_image_bytes(document_path, index)
        except Exception as exc:
            failure = SlideDescription(
                slide=slide,
                content="",
                status=DescriptionStatus.FAILED,
                error=f"No se pudo leer la diapositiva: {type(exc).__name__}: {exc}",
            )
            self.descriptions.save(failure)
            return failure

        self.descriptions.save(
            SlideDescription(slide=slide, content="", status=DescriptionStatus.PROCESSING)
        )
        description = self.generator.describe(
            slide=slide,
            slide_count=slide_count,
            subject=subject,
            image=image,
            pdf_page=pdf_page,
            layout=self._layout(document_path, index),
        )
        self.descriptions.save(description)

        self.telemetry.record(
            TelemetryEvent(
                name="precompute.slide",
                value=(self.clock.monotonic() - started) * 1000.0,
                unit="ms",
                attributes={
                    "deck_id": deck_id[:12],
                    "slide_number": slide.number,
                    "status": description.status.value,
                    "model": description.model,
                    "prompt_version": description.prompt_version,
                },
            )
        )
        return description

    def _layout(self, document_path: str, index: int) -> Mapping[str, Any] | None:

        extract = getattr(self.documents, "slide_layout", None)
        if not callable(extract):
            return None
        try:
            layout = extract(document_path, index)
        except Exception as exc:
            logger.debug("Sin geometria para la diapositiva %d: %s", index, exc)
            return None
        return layout if isinstance(layout, Mapping) else None

    def _run(
        self,
        deck_id: str,
        slide_count: int,
        document_path: str,
        subject: Subject,
        only_failed: bool,
    ) -> None:
        try:
            pending = self.descriptions.pending_slides(deck_id, slide_count)
            if only_failed:
                pending = [
                    index
                    for index in range(slide_count)
                    if (existing := self.descriptions.get(SlideIdentifier(DeckId(deck_id), index)))
                    is not None
                    and existing.status is DescriptionStatus.FAILED
                ]

            processed = 0
            for index in pending:
                self.describe_slide(
                    deck_id=deck_id,
                    index=index,
                    slide_count=slide_count,
                    document_path=document_path,
                    subject=subject,
                )
                processed += 1
                if self.policy.inter_slide_delay_seconds > 0:
                    time.sleep(self.policy.inter_slide_delay_seconds)
                if (
                    self.policy.cooldown_every_n_slides > 0
                    and processed % self.policy.cooldown_every_n_slides == 0
                    and self.policy.cooldown_seconds > 0
                ):
                    time.sleep(self.policy.cooldown_seconds)
        finally:
            self._inflight.discard(deck_id)

__all__ = [
    "PrecomputeDeck",
    "PrecomputePolicy",
    "PrecomputeProgress",
    "SlideContentSource",
]
