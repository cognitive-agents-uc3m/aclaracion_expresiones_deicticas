from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_NOISY = ("httpx", "httpcore", "urllib3", "google_genai.models", "asyncio", "multipart")

class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "severity": record.levelname,
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        telemetry = getattr(record, "telemetry", None)
        if telemetry:
            payload["telemetry"] = telemetry
        session_id = getattr(record, "session_id", None)
        if session_id:
            payload["session_id"] = session_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

class HumanFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        telemetry = getattr(record, "telemetry", None)
        if telemetry:
            metric = telemetry.get("metric")
            value = telemetry.get("value")
            unit = telemetry.get("unit") or ""
            return f"{base} | {metric}={value}{unit}"
        return base

def configure_logging(*, level: str = "INFO", fmt: str = "text") -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else HumanFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
