from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from ...domain.value_objects.identifiers import SessionId

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_.-]+")

class NullDeicticDetectionLog:
    def record_detection(
        self,
        *,
        session_id: SessionId,
        occurred_at: datetime,
        slide_number: int | None,
        expression_surface: str,
        expression_kind: str,
    ) -> None:
        return None

class FileDeicticDetectionLog:

    def __init__(self, data_dir: str | Path, *, directory_name: str = "deictic_timestamps"):
        self._dir = Path(data_dir) / directory_name
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, session_id: SessionId) -> Path:
        safe = _SAFE_FILENAME.sub("_", session_id.value).strip("._") or "session"
        return self._dir / f"{safe}.txt"

    def record_detection(
        self,
        *,
        session_id: SessionId,
        occurred_at: datetime,
        slide_number: int | None,
        expression_surface: str,
        expression_kind: str,
    ) -> None:
        slide = "" if slide_number is None else str(slide_number)
        line = (
            f"{occurred_at.isoformat()}\t"
            f"slide={slide}\t"
            f"kind={expression_kind}\t"
            f"expression={expression_surface}\n"
        )
        with self._lock:
            with self._path(session_id).open("a", encoding="utf-8", newline="") as handle:
                handle.write(line)

__all__ = ["FileDeicticDetectionLog", "NullDeicticDetectionLog"]
