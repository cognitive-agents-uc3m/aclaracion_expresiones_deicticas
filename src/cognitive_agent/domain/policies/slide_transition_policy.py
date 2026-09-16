from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..entities.student_interaction_state import PendingSlideTransition, StudentInteractionState
from ..entities.student_notes import StudentNotes
from ..value_objects.identifiers import SlideIdentifier

DEFAULT_IDLE_SECONDS = 2.0

class TagDecision(str, Enum):
    INSERT_NOW = "insert_now"

    SCHEDULE = "schedule"

    ALREADY_TAGGED = "already_tagged"

    NOT_APPLICABLE = "not_applicable"

@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    decision: TagDecision
    interaction: StudentInteractionState
    slide: SlideIdentifier | None = None

    @property
    def should_insert_now(self) -> bool:
        return self.decision is TagDecision.INSERT_NOW

    @property
    def is_scheduled(self) -> bool:
        return self.decision is TagDecision.SCHEDULE

class SlideTransitionPolicy:

    def __init__(self, *, idle_seconds: float = DEFAULT_IDLE_SECONDS) -> None:
        if idle_seconds < 0:
            raise ValueError("La espera de inactividad no puede ser negativa.")
        self._idle = timedelta(seconds=idle_seconds)

    @property
    def idle(self) -> timedelta:
        return self._idle

    @property
    def idle_seconds(self) -> float:
        return self._idle.total_seconds()

    def on_slide_changed(
        self,
        *,
        slide: SlideIdentifier,
        interaction: StudentInteractionState,
        notes: StudentNotes,
        now: datetime,
        tag_empty_notes: bool = False,
    ) -> TransitionOutcome:

        if notes.current_slide == slide:
            return TransitionOutcome(TagDecision.ALREADY_TAGGED, interaction.without_pending(), slide)

        if not notes.has_student_content and not tag_empty_notes:
            return TransitionOutcome(TagDecision.NOT_APPLICABLE, interaction.without_pending(), slide)

        if not interaction.is_writing(now=now, idle=self._idle):
            return TransitionOutcome(TagDecision.INSERT_NOW, interaction.without_pending(), slide)

        pending = PendingSlideTransition(slide=slide, requested_at=now, deadline=now + self._idle)
        return TransitionOutcome(TagDecision.SCHEDULE, interaction.with_pending(pending), slide)

    def on_keystroke(
        self, *, interaction: StudentInteractionState, now: datetime
    ) -> StudentInteractionState:

        return interaction.with_keystroke(at=now, idle=self._idle)

    def due_transition(
        self, *, interaction: StudentInteractionState, now: datetime
    ) -> PendingSlideTransition | None:

        pending = interaction.pending_transition
        if pending is None:
            return None
        if not pending.is_due(now):
            return None
        if interaction.is_writing(now=now, idle=self._idle):
            return None
        return pending

    def on_first_text(
        self, *, slide: SlideIdentifier | None, notes: StudentNotes
    ) -> TransitionOutcome:

        empty_interaction = StudentInteractionState()
        if slide is None or notes.current_slide == slide:
            return TransitionOutcome(TagDecision.NOT_APPLICABLE, empty_interaction, slide)
        return TransitionOutcome(TagDecision.INSERT_NOW, empty_interaction, slide)
