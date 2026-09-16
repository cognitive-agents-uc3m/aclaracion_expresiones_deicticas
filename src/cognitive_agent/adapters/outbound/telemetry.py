from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...application.ports.outbound.platform import TelemetryEvent

logger = logging.getLogger("cognitive_agent.telemetry")

_MAX_TEXT = 120

_FORBIDDEN = frozenset(
    {"audio", "audio_bytes", "notes", "notes_text", "student_text", "raw_audio", "transcript_full"}
)

class LoggingTelemetry:

    def __init__(self, *, redact_content: bool = True, enabled: bool = True) -> None:
        self._redact = redact_content
        self._enabled = enabled

    def record(self, event: TelemetryEvent) -> None:
        if not self._enabled:
            return
        payload = {
            "metric": event.name,
            "value": event.value,
            "unit": event.unit,
            "at": (event.occurred_at or datetime.now(timezone.utc)).isoformat(),
            **self._sanitize(event.attributes),
        }
        logger.info("telemetry", extra={"telemetry": payload})

    def record_latency(self, name: str, milliseconds: float, **attributes: Any) -> None:
        self.record(
            TelemetryEvent(
                name=name, value=round(float(milliseconds), 2), unit="ms", attributes=attributes
            )
        )

    def record_error(self, name: str, error: BaseException, **attributes: Any) -> None:
        self.record(
            TelemetryEvent(
                name=f"{name}.error",
                value=1.0,
                attributes={
                    "error_type": type(error).__name__,
                    "error": str(error)[:_MAX_TEXT],
                    **attributes,
                },
            )
        )

    def _sanitize(self, attributes: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in (attributes or {}).items():
            if key in _FORBIDDEN:
                continue
            if key == "session_id" and self._redact and isinstance(value, str):
                clean[key] = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
                continue
            if isinstance(value, str) and self._redact and len(value) > _MAX_TEXT:
                clean[key] = value[:_MAX_TEXT] + "..."
                continue
            clean[key] = value
        return clean

class JsonlTelemetry:

    def __init__(
        self, path: str | Path, *, redact_content: bool = True, enabled: bool = True
    ) -> None:
        self._path = Path(path)
        self._redact = redact_content
        self._enabled = enabled
        self._lock = threading.Lock()

    def record(self, event: TelemetryEvent) -> None:
        if not self._enabled:
            return
        payload = {
            "metric": event.name,
            "value": event.value,
            "unit": event.unit,
            "at": (event.occurred_at or datetime.now(timezone.utc)).isoformat(),
            **self._sanitize(event.attributes),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def record_latency(self, name: str, milliseconds: float, **attributes: Any) -> None:
        self.record(
            TelemetryEvent(
                name=name, value=round(float(milliseconds), 2), unit="ms", attributes=attributes
            )
        )

    def record_error(self, name: str, error: BaseException, **attributes: Any) -> None:
        self.record(
            TelemetryEvent(
                name=f"{name}.error",
                value=1.0,
                attributes={
                    "error_type": type(error).__name__,
                    "error": str(error)[:_MAX_TEXT],
                    **attributes,
                },
            )
        )

    def _sanitize(self, attributes: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in (attributes or {}).items():
            if key in _FORBIDDEN:
                continue
            if key == "session_id" and self._redact and isinstance(value, str):
                clean[key] = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
                continue
            if isinstance(value, str) and self._redact and len(value) > _MAX_TEXT:
                clean[key] = value[:_MAX_TEXT] + "..."
                continue
            clean[key] = value
        return clean

class CompositeTelemetry:

    def __init__(self, *sinks) -> None:
        self._sinks = tuple(sink for sink in sinks if sink is not None)

    def record(self, event: TelemetryEvent) -> None:
        for sink in self._sinks:
            sink.record(event)

    def record_latency(self, name: str, milliseconds: float, **attributes: Any) -> None:
        for sink in self._sinks:
            sink.record_latency(name, milliseconds, **attributes)

    def record_error(self, name: str, error: BaseException, **attributes: Any) -> None:
        for sink in self._sinks:
            sink.record_error(name, error, **attributes)

class NullTelemetry:
    def record(self, event: TelemetryEvent) -> None:
        return None

    def record_latency(self, name: str, milliseconds: float, **attributes: Any) -> None:
        return None

    def record_error(self, name: str, error: BaseException, **attributes: Any) -> None:
        return None

class RecordingTelemetry:

    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)

    def record_latency(self, name: str, milliseconds: float, **attributes: Any) -> None:
        self.record(TelemetryEvent(name=name, value=milliseconds, unit="ms", attributes=attributes))

    def record_error(self, name: str, error: BaseException, **attributes: Any) -> None:
        self.record(
            TelemetryEvent(
                name=f"{name}.error",
                value=1.0,
                attributes={"error_type": type(error).__name__, **attributes},
            )
        )

    def names(self) -> list[str]:
        return [e.name for e in self.events]

    def find(self, name: str) -> list[TelemetryEvent]:
        return [e for e in self.events if e.name == name]

    def reset(self) -> None:
        self.events.clear()
