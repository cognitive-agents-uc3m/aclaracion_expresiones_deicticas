from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from ..value_objects.identifiers import SlideIdentifier

@dataclass(frozen=True, slots=True)
class PendingSlideTransition:

    slide: SlideIdentifier
    requested_at: datetime
    deadline: datetime

    def rescheduled(self, *, now: datetime, idle: timedelta) -> "PendingSlideTransition":

        return replace(self, deadline=now + idle)

    def superseded_by(
        self, slide: SlideIdentifier, *, now: datetime, idle: timedelta
    ) -> "PendingSlideTransition":
        return PendingSlideTransition(slide=slide, requested_at=now, deadline=now + idle)

    def is_due(self, now: datetime) -> bool:
        return now >= self.deadline

    def remaining(self, now: datetime) -> timedelta:
        return max(timedelta(0), self.deadline - now)

@dataclass(frozen=True, slots=True)
class StudentInteractionState:
    last_keystroke_at: datetime | None = None
    pending_transition: PendingSlideTransition | None = None
    caret_slide: SlideIdentifier | None = None

    def is_writing(self, *, now: datetime, idle: timedelta) -> bool:

        if self.last_keystroke_at is None:
            return False
        return (now - self.last_keystroke_at) < idle

    def with_keystroke(self, *, at: datetime, idle: timedelta) -> "StudentInteractionState":

        pending = self.pending_transition
        if pending is not None:
            pending = pending.rescheduled(now=at, idle=idle)
        return replace(self, last_keystroke_at=at, pending_transition=pending)

    def with_pending(self, transition: PendingSlideTransition | None) -> "StudentInteractionState":
        return replace(self, pending_transition=transition)

    def without_pending(self) -> "StudentInteractionState":
        return replace(self, pending_transition=None)

    def with_caret_slide(self, slide: SlideIdentifier | None) -> "StudentInteractionState":
        return replace(self, caret_slide=slide)
