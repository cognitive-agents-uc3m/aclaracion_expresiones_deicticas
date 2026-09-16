from __future__ import annotations

from dataclasses import dataclass

from ...domain.entities.classroom_session import ClassroomSession
from ...domain.entities.slide import Deck
from ...domain.errors import SessionNotFound
from ...domain.events import DeckLoaded, SessionEnded, SessionStarted
from ...domain.value_objects.identifiers import DeckId, SessionId
from ..dto import (
    ChangeSlideCommand,
    LoadDeckCommand,
    RenameSessionCommand,
    SessionView,
    SlideView,
    StartSessionCommand,
)
from ..ports.outbound import (
    ClarificationRepository,
    ClockPort,
    EventPublisherPort,
    NotesRepository,
    SessionRepository,
    SlideDescriptionRepository,
)
from ..settings import ApplicationSettings
from ..views import session_view, slide_view

@dataclass(slots=True)
class StartClassroomSession:
    sessions: SessionRepository
    notes: NotesRepository
    clock: ClockPort
    events: EventPublisherPort
    settings: ApplicationSettings

    def execute(self, command: StartSessionCommand) -> SessionView:
        now = self.clock.now()
        session = ClassroomSession.start(
            subject=command.subject or self.settings.session.default_subject,
            at=now,
            transcript_window=self.settings.session.transcript_window,
            access_key=command.access_key,
            title=command.title,
            session_id=command.session_id,
        )
        self.sessions.create(session)

        notes = self.notes.get_or_create(session.session_id)
        notes.slide_tag_template = self.settings.notes.slide_tag_template
        notes.clarification_tag_template = self.settings.notes.clarification_tag_template
        self.notes.save(notes)

        self.events.publish(
            SessionStarted(
                occurred_at=now,
                session_id=session.session_id,
                subject=session.subject,
                title=session.title,
            )
        )
        return session_view(session)

@dataclass(slots=True)
class EndClassroomSession:
    sessions: SessionRepository
    clarifications: ClarificationRepository
    clock: ClockPort
    events: EventPublisherPort

    def execute(self, session_id: SessionId) -> SessionView:
        now = self.clock.now()
        with self.sessions.transaction(session_id) as session:
            started = session.started_at
            session.end(now)
            snapshot = session

        self.events.publish(
            SessionEnded(
                occurred_at=now,
                session_id=session_id,
                duration_seconds=(now - started).total_seconds() if started else 0.0,
            )
        )
        latest = self.clarifications.latest_for_session(session_id)
        return session_view(snapshot, latest=latest)

@dataclass(slots=True)
class RenameClassroomSession:

    sessions: SessionRepository
    clarifications: ClarificationRepository
    descriptions: SlideDescriptionRepository

    def execute(self, command: RenameSessionCommand) -> SessionView:
        with self.sessions.transaction(command.session_id) as session:
            session.rename(command.title)
            snapshot = session

        description = (
            self.descriptions.get(snapshot.current_slide) if snapshot.current_slide else None
        )
        latest = self.clarifications.latest_for_session(command.session_id)
        return session_view(snapshot, description=description, latest=latest)

@dataclass(slots=True)
class LoadDeck:
    sessions: SessionRepository
    descriptions: SlideDescriptionRepository
    clock: ClockPort
    events: EventPublisherPort

    def execute(self, command: LoadDeckCommand) -> SlideView:
        now = self.clock.now()
        deck = Deck(
            deck_id=DeckId(command.deck_id),
            slide_count=command.slide_count,
            title=command.title,
            source_name=command.source_name,
        )
        with self.sessions.transaction(command.session_id) as session:
            session.load_deck(deck)
            snapshot = session

        self.events.publish(
            DeckLoaded(
                occurred_at=now,
                session_id=command.session_id,
                slide_count=deck.slide_count,
                deck_title=deck.title,
            )
        )
        description = (
            self.descriptions.get(snapshot.current_slide) if snapshot.current_slide else None
        )
        return slide_view(snapshot, description)

@dataclass(slots=True)
class GetCurrentSlide:

    sessions: SessionRepository
    descriptions: SlideDescriptionRepository

    def execute(self, session_id: SessionId) -> SlideView:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(f"No existe la sesion {session_id}.")
        description = self.descriptions.get(session.current_slide) if session.current_slide else None
        return slide_view(session, description)

@dataclass(slots=True)
class GetSession:
    sessions: SessionRepository
    descriptions: SlideDescriptionRepository
    clarifications: ClarificationRepository

    def execute(self, session_id: SessionId) -> SessionView:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(f"No existe la sesion {session_id}.")
        description = self.descriptions.get(session.current_slide) if session.current_slide else None
        latest = self.clarifications.latest_for_session(session_id)
        return session_view(session, description=description, latest=latest)

__all__ = [
    "ChangeSlideCommand",
    "EndClassroomSession",
    "GetCurrentSlide",
    "GetSession",
    "LoadDeck",
    "RenameClassroomSession",
    "StartClassroomSession",
]
