from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..errors import NoActiveDeck, SessionAlreadyEnded
from ..value_objects.identifiers import ClarificationId, SessionId, SlideIdentifier
from ..value_objects.pointer import PointerPosition
from ..value_objects.subject import Subject
from ..value_objects.transcript import TranscriptContext, TranscriptFragment
from .slide import Deck
from .student_interaction_state import StudentInteractionState

@dataclass
class ClassroomSession:

    session_id: SessionId
    subject: Subject
    started_at: datetime
    access_key: str = ""
    title: str = ""
    deck: Deck | None = None
    current_slide: SlideIdentifier | None = None
    context: TranscriptContext = field(default_factory=TranscriptContext)
    interaction: StudentInteractionState = field(default_factory=StudentInteractionState)
    latest_clarification_id: ClarificationId | None = None
    pointer: PointerPosition | None = None

    ended_at: datetime | None = None
    version: int = 0

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def has_deck(self) -> bool:
        return self.deck is not None and not self.deck.is_empty

    @property
    def slide_count(self) -> int:
        return self.deck.slide_count if self.deck else 0

    @property
    def slide_label(self) -> str:

        if not self.has_deck or self.current_slide is None:
            return "Sin presentacion"
        return f"Diapositiva {self.current_slide.number} de {self.slide_count}"

    def require_deck(self) -> Deck:
        if self.deck is None or self.deck.is_empty:
            raise NoActiveDeck("La sesion todavia no tiene una presentacion cargada.")
        return self.deck

    def _require_active(self) -> None:
        if not self.is_active:
            raise SessionAlreadyEnded(f"La sesion {self.session_id} ya termino.")

    def load_deck(self, deck: Deck) -> SlideIdentifier | None:
        self._require_active()
        self.deck = deck
        self.current_slide = deck.slide_at(0) if not deck.is_empty else None
        self.context = self.context.cleared()
        self.interaction = self.interaction.without_pending()
        self.version += 1
        return self.current_slide

    def change_slide(self, index: int) -> SlideIdentifier:

        self._require_active()
        deck = self.require_deck()
        self.current_slide = deck.slide_at(deck.clamp(index))

        self.pointer = None
        self.version += 1
        return self.current_slide

    def point_at(self, x: float, y: float, *, at: datetime) -> PointerPosition | None:

        if self.current_slide is None:
            return None
        self.pointer = PointerPosition(x=x, y=y, at=at, slide=self.current_slide)
        self.version += 1
        return self.pointer

    def fresh_pointer(self, *, now: datetime, max_age_seconds: float = 8.0):

        from datetime import timedelta

        if self.pointer is None:
            return None
        if not self.pointer.applies_to(self.current_slide):
            return None
        if not self.pointer.is_fresh(now=now, max_age=timedelta(seconds=max_age_seconds)):
            return None
        return self.pointer

    def move_slide(self, delta: int) -> SlideIdentifier:
        deck = self.require_deck()
        base = self.current_slide.index if self.current_slide else 0
        return self.change_slide(base + int(delta))

    def observe_fragment(self, fragment: TranscriptFragment) -> TranscriptFragment:

        self._require_active()
        bound = fragment.bound_to(self.current_slide)
        self.context = self.context.append(bound)
        self.version += 1
        return bound

    def clear_context(self) -> None:
        self.context = self.context.cleared()
        self.version += 1

    def retain_context(
        self, count: int, *, slide: SlideIdentifier | None = None
    ) -> None:
        self.context = self.context.retain_latest(count, slide=slide)
        self.version += 1

    def remember_clarification(self, clarification_id: ClarificationId) -> None:
        self.latest_clarification_id = clarification_id
        self.version += 1

    def rename(self, title: str) -> str:
        self.title = (title or "").strip()[:200]
        self.version += 1
        return self.title

    def end(self, at: datetime) -> None:
        if self.is_active:
            self.ended_at = at
            self.version += 1

    @staticmethod
    def start(
        *,
        subject: Subject,
        at: datetime,
        transcript_window: int = 6,
        access_key: str = "",
        title: str = "",
        session_id: SessionId | None = None,
    ) -> "ClassroomSession":
        return ClassroomSession(
            session_id=session_id or SessionId.new(),
            subject=subject,
            started_at=at,
            access_key=access_key,
            title=title,
            context=TranscriptContext(max_size=transcript_window),
        )
