from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from ..value_objects.deictic import DeicticExpression
from ..value_objects.identifiers import ClarificationId, SessionId, SlideIdentifier
from ..value_objects.prompt import PromptRef

class ClarificationStatus(str, Enum):
    PENDING = "pending"

    READY = "ready"

    FAILED = "failed"

    TIMED_OUT = "timed_out"

    DISCARDED = "discarded"

    @property
    def is_terminal(self) -> bool:
        return self is not ClarificationStatus.PENDING

    @property
    def is_available_to_student(self) -> bool:
        return self is ClarificationStatus.READY

@dataclass(frozen=True, slots=True)
class Clarification:
    clarification_id: ClarificationId
    session_id: SessionId
    slide: SlideIdentifier
    trigger_fragment: str

    description_used: str

    recent_context: str = ""

    pointed_element: str = ""

    trigger_expression: DeicticExpression | None = None
    text: str = ""
    status: ClarificationStatus = ClarificationStatus.PENDING
    requested_at: datetime | None = None
    completed_at: datetime | None = None
    prompt_ref: PromptRef | None = None
    model: str = ""
    latency_ms: int | None = None
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    listened: bool = False
    inserted_into_notes: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

    def succeed(
        self,
        text: str,
        *,
        at: datetime,
        model: str = "",
        prompt_ref: PromptRef | None = None,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> "Clarification":
        return replace(
            self,
            text=text.strip(),
            status=ClarificationStatus.READY,
            completed_at=at,
            model=model or self.model,
            prompt_ref=prompt_ref or self.prompt_ref,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=None,
        )

    def fail(self, error: str, *, at: datetime, timed_out: bool = False) -> "Clarification":
        return replace(
            self,
            status=ClarificationStatus.TIMED_OUT if timed_out else ClarificationStatus.FAILED,
            completed_at=at,
            error=error[:500],
        )

    def discard(self, reason: str, *, at: datetime) -> "Clarification":
        return replace(
            self,
            status=ClarificationStatus.DISCARDED,
            completed_at=at,
            error=reason[:500],
        )

    def mark_listened(self) -> "Clarification":
        return replace(self, listened=True)

    def mark_inserted(self) -> "Clarification":
        return replace(self, inserted_into_notes=True)

    @property
    def is_available(self) -> bool:
        return self.status.is_available_to_student and bool(self.text.strip())

    def is_stale_for(self, current_slide: SlideIdentifier | None) -> bool:

        return current_slide is not None and current_slide != self.slide

    @staticmethod
    def requested(
        *,
        session_id: SessionId,
        slide: SlideIdentifier,
        trigger_fragment: str,
        description_used: str,
        recent_context: str = "",
        pointed_element: str = "",
        trigger_expression: DeicticExpression | None = None,
        at: datetime,
        prompt_ref: PromptRef | None = None,
        model: str = "",
        clarification_id: ClarificationId | None = None,
    ) -> "Clarification":
        return Clarification(
            clarification_id=clarification_id or ClarificationId.new(),
            session_id=session_id,
            slide=slide,
            trigger_fragment=trigger_fragment,
            description_used=description_used,
            recent_context=recent_context,
            pointed_element=pointed_element,
            trigger_expression=trigger_expression,
            status=ClarificationStatus.PENDING,
            requested_at=at,
            prompt_ref=prompt_ref,
            model=model,
        )
