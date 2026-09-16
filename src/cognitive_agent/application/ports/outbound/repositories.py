from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from ....domain.entities.clarification import Clarification
from ....domain.entities.classroom_session import ClassroomSession
from ....domain.entities.student_notes import StudentNotes
from ....domain.value_objects.identifiers import (
    ClarificationId,
    SessionId,
    SlideIdentifier,
)
from ....domain.value_objects.slide_description import SlideDescription

@runtime_checkable
class SessionRepository(Protocol):
    def create(self, session: ClassroomSession) -> ClassroomSession: ...

    def get(self, session_id: SessionId) -> ClassroomSession | None: ...

    def require(self, session_id: SessionId) -> ClassroomSession:

        ...

    def save(self, session: ClassroomSession) -> None: ...

    def delete(self, session_id: SessionId) -> None: ...

    def list_active(self) -> list[ClassroomSession]: ...

    def find_by_access_key(self, key: str) -> ClassroomSession | None: ...

    def transaction(self, session_id: SessionId) -> AbstractContextManager[ClassroomSession]:

        ...

@runtime_checkable
class NotesRepository(Protocol):
    def get(self, session_id: SessionId) -> StudentNotes | None: ...

    def get_or_create(self, session_id: SessionId) -> StudentNotes: ...

    def save(self, notes: StudentNotes) -> None: ...

    def delete(self, session_id: SessionId) -> None: ...

    def transaction(self, session_id: SessionId) -> AbstractContextManager[StudentNotes]: ...

@runtime_checkable
class SlideDescriptionRepository(Protocol):

    def get(self, slide: SlideIdentifier) -> SlideDescription | None: ...

    def save(self, description: SlideDescription) -> None: ...

    def deck_progress(self, deck_id: str) -> tuple[int, int, int, int]:

        ...

    def pending_slides(self, deck_id: str, slide_count: int) -> list[int]: ...

@runtime_checkable
class ClarificationRepository(Protocol):
    def save(self, clarification: Clarification) -> None: ...

    def get(self, clarification_id: ClarificationId) -> Clarification | None: ...

    def latest_for_session(self, session_id: SessionId) -> Clarification | None:

        ...

    def list_for_session(self, session_id: SessionId, *, limit: int = 50) -> list[Clarification]: ...
