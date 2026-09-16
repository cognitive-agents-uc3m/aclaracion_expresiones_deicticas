from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import asdict
from ...application.ports.outbound.platform import Notification, NotificationChannel
from ...domain.value_objects.identifiers import SessionId

class LiveRegionNotificationHub:

    def __init__(self, *, max_per_session: int = 50) -> None:
        self._queues: dict[str, deque[Notification]] = defaultdict(
            lambda: deque(maxlen=max_per_session)
        )
        self._lock = threading.Lock()

    def notify(self, notification: Notification) -> None:
        if notification.session_id is None:
            return
        with self._lock:
            self._queues[notification.session_id.value].append(notification)

    def drain(self, session_id: SessionId) -> list[Notification]:

        with self._lock:
            queue = self._queues.get(session_id.value)
            if not queue:
                return []
            drained = list(queue)
            queue.clear()
            return drained

    def peek(self, session_id: SessionId) -> list[Notification]:
        with self._lock:
            queue = self._queues.get(session_id.value)
            return list(queue) if queue else []

    def clear(self, session_id: SessionId) -> None:
        with self._lock:
            self._queues.pop(session_id.value, None)

    @staticmethod
    def to_payload(notification: Notification) -> dict:
        return {
            "message": notification.message,
            "level": notification.level.value,
            "channels": [c.value for c in notification.channels],
            "politeness": notification.politeness,
            "payload": dict(notification.payload),
        }

class CompositeNotificationPort:

    def __init__(self, *ports: object) -> None:
        self._ports = ports

    def notify(self, notification: Notification) -> None:
        for port in self._ports:
            notify = getattr(port, "notify", None)
            if callable(notify):
                notify(notification)

class NullNotificationPort:
    def notify(self, notification: Notification) -> None:
        return None

class RecordingNotificationPort:

    def __init__(self) -> None:
        self.notifications: list[Notification] = []

    def notify(self, notification: Notification) -> None:
        self.notifications.append(notification)

    @property
    def messages(self) -> list[str]:
        return [n.message for n in self.notifications]

    def with_channel(self, channel: NotificationChannel) -> list[Notification]:
        return [n for n in self.notifications if channel in n.channels]

    def as_dicts(self) -> list[dict]:
        return [asdict(n) for n in self.notifications]

    def reset(self) -> None:
        self.notifications.clear()
