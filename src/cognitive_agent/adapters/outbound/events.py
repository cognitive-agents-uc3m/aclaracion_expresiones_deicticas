from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable, Iterable
from ...domain.events import DomainEvent
from ...domain.value_objects.identifiers import SessionId

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], None]

class InProcessEventBus:
    def __init__(self, *, history_size: int = 200) -> None:
        self._handlers: list[tuple[EventHandler, tuple[type, ...] | None]] = []
        self._lock = threading.RLock()
        self._history: dict[str, deque[DomainEvent]] = {}
        self._history_size = history_size

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            handlers = list(self._handlers)
            key = event.session_id.value
            bucket = self._history.setdefault(key, deque(maxlen=self._history_size))
            bucket.append(event)

        for handler, event_types in handlers:
            if event_types is not None and not isinstance(event, event_types):
                continue
            try:
                handler(event)
            except Exception:
                logger.exception("Fallo un suscriptor del evento %s", event.name)

    def subscribe(
        self, handler: EventHandler, *, event_types: tuple[type, ...] | None = None
    ) -> Callable[[], None]:
        entry = (handler, event_types)
        with self._lock:
            self._handlers.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._handlers:
                    self._handlers.remove(entry)

        return unsubscribe

    def history(self, session_id: SessionId, *, since: int = 0) -> list[DomainEvent]:

        with self._lock:
            bucket = self._history.get(session_id.value)
            events = list(bucket) if bucket else []
        return events[since:]

    def clear(self, session_id: SessionId | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._history.clear()
            else:
                self._history.pop(session_id.value, None)

    def handler_count(self) -> int:
        with self._lock:
            return len(self._handlers)

class RecordingEventBus(InProcessEventBus):

    def __init__(self) -> None:
        super().__init__(history_size=10_000)
        self.recorded: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.recorded.append(event)
        super().publish(event)

    def of_type(self, *types: type) -> list[DomainEvent]:
        return [e for e in self.recorded if isinstance(e, types)]

    def names(self) -> list[str]:
        return [e.name for e in self.recorded]

    def reset(self) -> None:
        self.recorded.clear()
        self.clear()

def event_to_dict(event: DomainEvent) -> dict:

    from dataclasses import fields

    payload: dict = {"event": event.name}
    for f in fields(event):
        value = getattr(event, f.name)
        payload[f.name] = _serialize(value)
    return payload

def _serialize(value: object):
    from dataclasses import asdict, is_dataclass
    from datetime import datetime
    from enum import Enum

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, SessionId):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return {k: _serialize(v) for k, v in asdict(value).items()}
        except Exception:
            return str(value)
    if isinstance(value, Iterable):
        return [_serialize(v) for v in value]
    return str(value)
