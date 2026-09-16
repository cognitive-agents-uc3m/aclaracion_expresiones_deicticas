from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from ....domain.events import DomainEvent
from ....domain.value_objects.identifiers import SessionId

@runtime_checkable
class ClockPort(Protocol):

    def now(self) -> datetime: ...

    def monotonic(self) -> float:

        ...

@runtime_checkable
class TaskHandle(Protocol):
    def cancel(self) -> bool: ...

    @property
    def done(self) -> bool: ...

@runtime_checkable
class TaskSchedulerPort(Protocol):

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> TaskHandle: ...

    def schedule_after(
        self, delay_seconds: float, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> TaskHandle:

        ...

    def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:

        ...

EventHandler = Callable[[DomainEvent], None]

@runtime_checkable
class EventPublisherPort(Protocol):
    def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, handler: EventHandler, *, event_types: tuple[type, ...] | None = None) -> Callable[[], None]:

        ...

class NotificationLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

class NotificationChannel(str, Enum):
    LIVE_REGION = "live_region"

    SOUND = "sound"

    SPEECH = "speech"

@dataclass(frozen=True, slots=True)
class Notification:

    message: str
    level: NotificationLevel = NotificationLevel.INFO
    channels: tuple[NotificationChannel, ...] = (NotificationChannel.LIVE_REGION,)
    politeness: str = "polite"

    session_id: SessionId | None = None
    payload: dict[str, Any] = field(default_factory=dict)

@runtime_checkable
class NotificationPort(Protocol):
    def notify(self, notification: Notification) -> None: ...

@runtime_checkable
class DeicticDetectionLogPort(Protocol):

    def record_detection(
        self,
        *,
        session_id: SessionId,
        occurred_at: datetime,
        slide_number: int | None,
        expression_surface: str,
        expression_kind: str,
    ) -> None: ...

@dataclass(frozen=True, slots=True)
class TelemetryEvent:

    name: str
    value: float | None = None
    unit: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime | None = None

@runtime_checkable
class TelemetryPort(Protocol):
    def record(self, event: TelemetryEvent) -> None: ...

    def record_latency(self, name: str, milliseconds: float, **attributes: Any) -> None: ...

    def record_error(self, name: str, error: BaseException, **attributes: Any) -> None: ...
