from __future__ import annotations

from dataclasses import dataclass

from ...domain.entities.clarification import Clarification
from ...domain.errors import (
    ClarificationNotFound,
    NoClarificationAvailable,
    SessionNotFound,
)
from ...domain.events import (
    ClarificationInsertedIntoNotes,
    NotesExported,
    NotesUpdated,
    SlideTagInserted,
)
from ...domain.policies import (
    ClarificationInsertionPolicy,
    NoteTaggingPolicy,
    SlideTransitionPolicy,
    TagDecision,
)
from ...domain.services.notes_projection import NotesProjection
from ...domain.value_objects.identifiers import SessionId, SlideIdentifier
from ..dto import (
    ExportedNotes,
    ExportNotesCommand,
    InsertClarificationCommand,
    NotesView,
    UpdateNotesCommand,
)
from ..ports.outbound import (
    ClarificationRepository,
    ClockPort,
    EventPublisherPort,
    NotesExporterPort,
    NotesProcessorPort,
    NotesRepository,
    Notification,
    NotificationChannel,
    NotificationLevel,
    NotificationPort,
    SessionRepository,
    TaskSchedulerPort,
    TelemetryEvent,
    TelemetryPort,
)
from ..settings import ApplicationSettings
from ..views import notes_view

_PROCESSED_DISCLAIMER = (
    "Este documento ha sido reformateado automáticamente para facilitar su lectura. "
    "El texto original que escribiste se conserva íntegro y sin modificar al final "
    "del documento, en el apartado 'Versión original'."
)

@dataclass(slots=True)
class ScheduleSlideTagInsertion:

    sessions: SessionRepository
    notes: NotesRepository
    clock: ClockPort
    events: EventPublisherPort
    scheduler: TaskSchedulerPort
    transitions: SlideTransitionPolicy
    tagging: NoteTaggingPolicy
    notifications: NotificationPort
    settings: ApplicationSettings

    def execute(self, session_id: SessionId, slide: SlideIdentifier) -> TagDecision:
        now = self.clock.now()
        notes = self.notes.get_or_create(session_id)

        with self.sessions.transaction(session_id) as session:
            outcome = self.transitions.on_slide_changed(
                slide=slide,
                interaction=session.interaction,
                notes=notes,
                now=now,
                tag_empty_notes=self.settings.notes.tag_empty_notes,
            )
            session.interaction = outcome.interaction

        if outcome.decision is TagDecision.INSERT_NOW:
            self._insert(session_id, slide, scheduled=False)
        elif outcome.decision is TagDecision.SCHEDULE:

            self.scheduler.schedule_after(
                self.transitions.idle_seconds + 0.05,
                FlushPendingSlideTag.of(self).execute,
                session_id,
            )
        return outcome.decision

    def _insert(self, session_id: SessionId, slide: SlideIdentifier, *, scheduled: bool) -> None:
        now = self.clock.now()
        with self.notes.transaction(session_id) as notes:
            result = self.tagging.apply(notes=notes, slide=slide, at=now)
        if not result.did_insert or result.inserted is None:
            return

        with self.sessions.transaction(session_id) as session:
            session.interaction = session.interaction.without_pending().with_caret_slide(slide)

        self.events.publish(
            SlideTagInserted(
                occurred_at=now,
                session_id=session_id,
                entry_id=result.inserted.entry_id,
                slide=slide,
                scheduled=scheduled,
            )
        )
        if result.announcement and self.settings.accessibility.announce_slide_changes:
            self.notifications.notify(
                Notification(
                    message=result.announcement,
                    level=NotificationLevel.INFO,
                    channels=(NotificationChannel.LIVE_REGION,),
                    politeness=self.settings.accessibility.live_region_politeness,
                    session_id=session_id,
                )
            )

@dataclass(slots=True)
class FlushPendingSlideTag:

    parent: ScheduleSlideTagInsertion

    @staticmethod
    def of(parent: ScheduleSlideTagInsertion) -> "FlushPendingSlideTag":
        return FlushPendingSlideTag(parent=parent)

    def execute(self, session_id: SessionId) -> bool:
        now = self.parent.clock.now()
        session = self.parent.sessions.get(session_id)
        if session is None or not session.is_active:
            return False

        pending = session.interaction.pending_transition
        if pending is None:
            return False

        due = self.parent.transitions.due_transition(interaction=session.interaction, now=now)
        if due is None:
            remaining = max(0.1, pending.remaining(now).total_seconds() + 0.05)
            self.parent.scheduler.schedule_after(remaining, self.execute, session_id)
            return False

        self.parent._insert(session_id, due.slide, scheduled=True)
        return True

@dataclass(slots=True)
class UpdateStudentNotes:

    sessions: SessionRepository
    notes: NotesRepository
    clock: ClockPort
    events: EventPublisherPort
    transitions: SlideTransitionPolicy
    tagging: NoteTaggingPolicy
    telemetry: TelemetryPort
    settings: ApplicationSettings

    def execute(self, command: UpdateNotesCommand) -> NotesView:
        now = self.clock.now()
        session = self.sessions.get(command.session_id)
        if session is None:
            raise SessionNotFound(f"No existe la sesion {command.session_id}.")

        announcement = ""
        inserted: tuple[str, ...] = ()
        with self.notes.transaction(command.session_id) as notes:
            had_content = notes.has_student_content
            result = NotesProjection.reconcile(notes, command.text, at=now)

            if (
                not had_content
                and notes.has_student_content
                and notes.current_slide is None
                and session.current_slide is not None
            ):
                entrada = notes.insert_slide_tag_at_start(session.current_slide, at=now)

                if entrada is not None:
                    inserted = (entrada.render(),)

            if result.repaired:
                announcement = (
                    "Se ha restaurado una marca de diapositiva que se habia borrado."
                )
            snapshot = notes

        if command.is_keystroke:
            with self.sessions.transaction(command.session_id) as live:
                live.interaction = self.transitions.on_keystroke(
                    interaction=live.interaction, now=now
                )

        if result.changed:
            self.events.publish(
                NotesUpdated(
                    occurred_at=now,
                    session_id=command.session_id,
                    entry_count=len(snapshot.entries),
                    restored_markers=result.restored_markers,
                )
            )
        if result.repaired:
            self.telemetry.record(
                TelemetryEvent(
                    name="notes.marker_restored",
                    value=float(len(result.restored_markers)),
                    attributes={"session_id": command.session_id.value},
                    occurred_at=now,
                )
            )

        return notes_view(
            snapshot,
            restored_markers=result.restored_markers,
            inserted_markers=inserted,
            announcement=announcement,
        )

@dataclass(slots=True)
class InsertClarificationIntoNotes:

    sessions: SessionRepository
    notes: NotesRepository
    clarifications: ClarificationRepository
    clock: ClockPort
    events: EventPublisherPort
    insertion: ClarificationInsertionPolicy
    notifications: NotificationPort
    telemetry: TelemetryPort
    settings: ApplicationSettings

    def execute(self, command: InsertClarificationCommand) -> NotesView:
        now = self.clock.now()
        clarification = self._resolve(command)

        with self.notes.transaction(command.session_id) as notes:
            outcome = self.insertion.apply(
                notes=notes,
                clarification=clarification,
                at=now,
                requested_by_student=command.requested_by_student,
            )
            snapshot = notes

        if outcome.did_insert and clarification is not None and outcome.entry is not None:
            self.clarifications.save(clarification.mark_inserted())
            self.events.publish(
                ClarificationInsertedIntoNotes(
                    occurred_at=now,
                    session_id=command.session_id,
                    entry_id=outcome.entry.entry_id,
                    clarification_id=clarification.clarification_id,
                    slide=clarification.slide,
                )
            )
            self.telemetry.record(
                TelemetryEvent(
                    name="clarification.inserted",
                    value=1.0,
                    attributes={
                        "session_id": command.session_id.value,
                        "slide_number": clarification.slide.number,
                    },
                    occurred_at=now,
                )
            )

        if outcome.announcement:

            self.notifications.notify(
                Notification(
                    message=outcome.announcement,
                    level=(
                        NotificationLevel.SUCCESS
                        if outcome.did_insert
                        else NotificationLevel.WARNING
                    ),
                    channels=(NotificationChannel.LIVE_REGION,),
                    politeness=self.settings.accessibility.clarification_politeness,
                    session_id=command.session_id,
                )
            )

        return notes_view(snapshot, announcement=outcome.announcement)

    def _resolve(self, command: InsertClarificationCommand) -> Clarification | None:
        if command.clarification_id is not None:
            found = self.clarifications.get(command.clarification_id)
            if found is None:
                raise ClarificationNotFound(f"No existe la aclaracion {command.clarification_id}.")
            return found
        return self.clarifications.latest_for_session(command.session_id)

@dataclass(slots=True)
class JumpToSlideNotes:

    sessions: SessionRepository
    notes: NotesRepository
    notifications: NotificationPort
    settings: ApplicationSettings

    def execute(self, session_id: SessionId, *, slide_index: int | None = None) -> NotesView:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(f"No existe la sesion {session_id}.")

        notes = self.notes.get_or_create(session_id)
        target: SlideIdentifier | None
        if slide_index is None:
            target = session.current_slide
        elif session.deck is not None:
            target = session.deck.slide_at(session.deck.clamp(slide_index))
        else:
            target = None

        if target is None:
            return notes_view(notes, announcement="No hay ninguna diapositiva activa.")

        offset = NotesProjection.caret_offset_for_slide(notes, target)
        if offset is None:
            message = (
                f"Todavia no has escrito nada en la diapositiva {target.number}. "
                "El cursor se queda donde estaba."
            )
            self._announce(message, session_id)
            return notes_view(notes, announcement=message)

        message = f"Cursor en tus apuntes de la diapositiva {target.number}."
        self._announce(message, session_id)
        return notes_view(notes, caret_offset=offset, announcement=message)

    def _announce(self, message: str, session_id: SessionId) -> None:
        self.notifications.notify(
            Notification(
                message=message,
                channels=(NotificationChannel.LIVE_REGION,),
                politeness=self.settings.accessibility.clarification_politeness,
                session_id=session_id,
            )
        )

@dataclass(slots=True)
class ExportNotes:

    notes: NotesRepository
    sessions: SessionRepository
    clock: ClockPort
    events: EventPublisherPort
    exporters: dict[str, NotesExporterPort]
    processor: NotesProcessorPort | None
    telemetry: TelemetryPort

    def execute(self, command: ExportNotesCommand) -> ExportedNotes:
        now = self.clock.now()
        notes = self.notes.get_or_create(command.session_id)
        session = self.sessions.get(command.session_id)
        title = session.title if session else ""
        subject = session.subject if session else None

        exporter = self.exporters.get(command.fmt) or next(iter(self.exporters.values()))

        processed_text: str | None = None
        if command.processed:
            if self.processor is None:

                processed_text = None
            else:
                started = self.clock.monotonic()
                raw = notes.render_raw()
                try:
                    processed_text = self.processor.process(
                        raw, subject=subject if subject else None
                    )
                except Exception as exc:
                    self.telemetry.record_error("notes.process", exc)
                    processed_text = None
                else:
                    self.telemetry.record_latency(
                        "notes.process", (self.clock.monotonic() - started) * 1000.0
                    )

        document = exporter.export(notes, title=title, processed_text=processed_text)
        self.events.publish(
            NotesExported(
                occurred_at=now,
                session_id=command.session_id,
                fmt=exporter.fmt,
                processed=processed_text is not None,
                entry_count=len(notes.entries),
            )
        )
        return document

__all__ = [
    "ExportNotes",
    "FlushPendingSlideTag",
    "InsertClarificationIntoNotes",
    "JumpToSlideNotes",
    "NoClarificationAvailable",
    "ScheduleSlideTagInsertion",
    "UpdateStudentNotes",
    "_PROCESSED_DISCLAIMER",
]
