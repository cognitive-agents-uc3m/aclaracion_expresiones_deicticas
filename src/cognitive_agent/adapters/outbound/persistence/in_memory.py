from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

from ....domain.entities.clarification import Clarification
from ....domain.entities.classroom_session import ClassroomSession
from ....domain.entities.student_notes import StudentNotes
from ....domain.errors import SessionNotFound
from ....domain.value_objects.identifiers import (
    ClarificationId,
    SessionId,
    SlideIdentifier,
)
from ....domain.value_objects.slide_description import SlideDescription

class _LockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def for_key(self, key: str) -> threading.RLock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._locks[key] = lock
            return lock

    def discard(self, key: str) -> None:
        with self._guard:
            self._locks.pop(key, None)

class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, ClassroomSession] = {}
        self._locks = _LockRegistry()
        self._guard = threading.RLock()

    def create(self, session: ClassroomSession) -> ClassroomSession:
        with self._guard:
            self._sessions[session.session_id.value] = session
        self._persist(session)
        return session

    def get(self, session_id: SessionId) -> ClassroomSession | None:
        with self._guard:
            return self._sessions.get(session_id.value)

    def require(self, session_id: SessionId) -> ClassroomSession:
        session = self.get(session_id)
        if session is None:
            raise SessionNotFound(f"No existe la sesion {session_id}.")
        return session

    def save(self, session: ClassroomSession) -> None:
        with self._guard:
            self._sessions[session.session_id.value] = session
        self._persist(session)

    def delete(self, session_id: SessionId) -> None:
        with self._guard:
            self._sessions.pop(session_id.value, None)
        self._locks.discard(session_id.value)
        self._forget(session_id)

    def list_active(self) -> list[ClassroomSession]:
        with self._guard:
            return [s for s in self._sessions.values() if s.is_active]

    def find_by_access_key(self, key: str) -> ClassroomSession | None:
        clean = (key or "").strip()
        if not clean:
            return None
        with self._guard:
            for session in self._sessions.values():
                if session.is_active and session.access_key == clean:
                    return session
        return None

    @contextmanager
    def transaction(self, session_id: SessionId) -> Iterator[ClassroomSession]:
        lock = self._locks.for_key(session_id.value)
        with lock:
            session = self.require(session_id)
            yield session
            self.save(session)

    def _persist(self, session: ClassroomSession) -> None:
        return None

    def _forget(self, session_id: SessionId) -> None:
        return None

class InMemoryNotesRepository:
    def __init__(
        self,
        *,
        slide_tag_template: str | None = None,
        clarification_tag_template: str | None = None,
    ) -> None:
        self._notes: dict[str, StudentNotes] = {}
        self._locks = _LockRegistry()
        self._guard = threading.RLock()
        self._slide_tag_template = slide_tag_template
        self._clarification_tag_template = clarification_tag_template

    def get(self, session_id: SessionId) -> StudentNotes | None:
        with self._guard:
            return self._notes.get(session_id.value)

    def get_or_create(self, session_id: SessionId) -> StudentNotes:
        with self._guard:
            notes = self._notes.get(session_id.value)
            if notes is None:
                kwargs = {}
                if self._slide_tag_template:
                    kwargs["slide_tag_template"] = self._slide_tag_template
                if self._clarification_tag_template:
                    kwargs["clarification_tag_template"] = self._clarification_tag_template
                notes = StudentNotes.empty(session_id, **kwargs)
                self._notes[session_id.value] = notes
            return notes

    def save(self, notes: StudentNotes) -> None:
        with self._guard:
            self._notes[notes.session_id.value] = notes
        self._persist(notes)

    def delete(self, session_id: SessionId) -> None:
        with self._guard:
            self._notes.pop(session_id.value, None)
        self._locks.discard(session_id.value)

    @contextmanager
    def transaction(self, session_id: SessionId) -> Iterator[StudentNotes]:
        lock = self._locks.for_key(session_id.value)
        with lock:
            notes = self.get_or_create(session_id)
            yield notes
            self.save(notes)

    def _persist(self, notes: StudentNotes) -> None:
        return None

class InMemoryClarificationRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Clarification] = {}
        self._by_session: dict[str, list[str]] = defaultdict(list)
        self._guard = threading.RLock()

    def save(self, clarification: Clarification) -> None:
        key = clarification.clarification_id.value
        with self._guard:
            if key not in self._by_id:
                self._by_session[clarification.session_id.value].append(key)
            self._by_id[key] = clarification
        self._persist(clarification)

    def get(self, clarification_id: ClarificationId) -> Clarification | None:
        with self._guard:
            return self._by_id.get(clarification_id.value)

    def latest_for_session(self, session_id: SessionId) -> Clarification | None:

        with self._guard:
            keys = list(self._by_session.get(session_id.value, ()))
            for key in reversed(keys):
                candidate = self._by_id.get(key)
                if candidate is not None and candidate.is_available:
                    return candidate
        return None

    def list_for_session(self, session_id: SessionId, *, limit: int = 50) -> list[Clarification]:
        with self._guard:
            keys = list(self._by_session.get(session_id.value, ()))[-limit:]
            return [self._by_id[k] for k in keys if k in self._by_id]

    def delete_for_session(self, session_id: SessionId) -> None:
        with self._guard:
            keys = self._by_session.pop(session_id.value, [])
            for key in keys:
                self._by_id.pop(key, None)

    def _persist(self, clarification: Clarification) -> None:
        return None

class InMemorySlideDescriptionRepository:
    def __init__(self) -> None:
        self._descriptions: dict[str, SlideDescription] = {}
        self._guard = threading.RLock()

    @staticmethod
    def _key(slide: SlideIdentifier) -> str:
        return f"{slide.deck_id.value}#{slide.index}"

    def get(self, slide: SlideIdentifier) -> SlideDescription | None:
        with self._guard:
            return self._descriptions.get(self._key(slide))

    def save(self, description: SlideDescription) -> None:
        with self._guard:
            self._descriptions[self._key(description.slide)] = description

    def deck_progress(self, deck_id: str) -> tuple[int, int, int, int]:
        from ....domain.value_objects.slide_description import DescriptionStatus

        ready = failed = processing = total = 0
        with self._guard:
            for key, description in self._descriptions.items():
                if not key.startswith(f"{deck_id}#"):
                    continue
                total += 1
                if description.status is DescriptionStatus.READY:
                    ready += 1
                elif description.status is DescriptionStatus.FAILED:
                    failed += 1
                elif description.status is DescriptionStatus.PROCESSING:
                    processing += 1
        return ready, total, failed, processing

    def pending_slides(self, deck_id: str, slide_count: int) -> list[int]:
        from ....domain.value_objects.slide_description import DescriptionStatus

        pending: list[int] = []
        with self._guard:
            for index in range(slide_count):
                found = self._descriptions.get(f"{deck_id}#{index}")
                if found is None or found.status is not DescriptionStatus.READY:
                    pending.append(index)
        return pending
