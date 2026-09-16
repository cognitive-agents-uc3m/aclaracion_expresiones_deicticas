from __future__ import annotations

from dataclasses import dataclass

from ...domain.errors import NoActiveDeck
from ...domain.events import SlideChanged
from ..dto import ChangeSlideCommand, SlideView
from ..ports.outbound import (
    ClockPort,
    EventPublisherPort,
    Notification,
    NotificationChannel,
    NotificationPort,
    SessionRepository,
    SlideDescriptionRepository,
)
from ..settings import ApplicationSettings
from ..views import slide_view
from .notes import ScheduleSlideTagInsertion

@dataclass(slots=True)
class ChangeCurrentSlide:
    sessions: SessionRepository
    descriptions: SlideDescriptionRepository
    clock: ClockPort
    events: EventPublisherPort
    notifications: NotificationPort
    schedule_tag: ScheduleSlideTagInsertion
    settings: ApplicationSettings

    def execute(self, command: ChangeSlideCommand) -> SlideView:
        now = self.clock.now()

        with self.sessions.transaction(command.session_id) as session:
            previous = session.current_slide
            if session.deck is None or session.deck.is_empty:
                raise NoActiveDeck("No hay presentacion cargada en la sesion.")
            if command.index is not None:
                current = session.change_slide(command.index)
            elif command.delta is not None:
                current = session.move_slide(command.delta)
            else:
                current = session.current_slide or session.deck.slide_at(0)
            snapshot = session

        changed = previous != current
        if changed:
            self.events.publish(
                SlideChanged(
                    occurred_at=now,
                    session_id=command.session_id,
                    slide=current,
                    previous=previous,
                    slide_count=snapshot.slide_count,
                )
            )
            if self.settings.accessibility.announce_slide_changes:

                self.notifications.notify(
                    Notification(
                        message=f"Diapositiva {current.number} de {snapshot.slide_count}.",
                        channels=(NotificationChannel.LIVE_REGION,),
                        politeness=self.settings.accessibility.live_region_politeness,
                        session_id=command.session_id,
                        payload={"slide_number": current.number, "slide_index": current.index},
                    )
                )
            self.schedule_tag.execute(command.session_id, current)

        description = self.descriptions.get(current)
        return slide_view(snapshot, description)

__all__ = ["ChangeCurrentSlide"]
