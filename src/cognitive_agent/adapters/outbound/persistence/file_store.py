from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from ....domain.entities.clarification import Clarification
from ....domain.entities.classroom_session import ClassroomSession
from ....domain.entities.student_notes import StudentNotes
from ....domain.value_objects.identifiers import ClarificationId, SessionId
from .in_memory import (
    InMemoryClarificationRepository,
    InMemoryNotesRepository,
    InMemorySessionRepository,
)
from .serialization import (
    clarification_from_dict,
    clarification_to_dict,
    notes_from_dict,
    notes_to_dict,
    session_from_dict,
    session_to_dict,
)

logger = logging.getLogger(__name__)

_REINTENTOS_ESCRITURA = 6
_ESPERA_REINTENTO = 0.02

def _atomic_write(path: Path, payload: dict) -> None:

    import time as _time

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)

        ultimo: OSError | None = None
        for intento in range(_REINTENTOS_ESCRITURA):
            try:
                os.replace(tmp_name, path)
                return
            except PermissionError as exc:
                ultimo = exc
                _time.sleep(_ESPERA_REINTENTO * (intento + 1))
        raise ultimo if ultimo else OSError(f"No se pudo escribir {path}")
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("No se pudo leer %s; se ignora.", path)
        return None

def _mtime(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None

class _CrossProcessReload:

    def _watched_path(self, key: str) -> Path:
        raise NotImplementedError

    def _adopt(self, key: str, data: dict) -> None:
        raise NotImplementedError

    def _refresh(self, key: str) -> None:
        path = self._watched_path(key)
        actual = _mtime(path)
        if actual is None or self._seen.get(key) == actual:
            return
        data = _read(path)
        if data is None:
            return
        try:
            self._adopt(key, data)
        except Exception:
            logger.exception("No se pudo recargar %s; se conserva lo que hay en memoria.", path)
            return
        self._seen[key] = actual

    def _mark_written(self, key: str) -> None:
        marca = _mtime(self._watched_path(key))
        if marca is not None:
            self._seen[key] = marca

class FileSessionRepository(InMemorySessionRepository, _CrossProcessReload):
    def __init__(self, data_dir: Path | str) -> None:
        super().__init__()
        self._dir = Path(data_dir) / "sessions"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._io_lock = threading.Lock()
        self._seen: dict[str, int] = {}
        self._restore()

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _watched_path(self, key: str) -> Path:
        return self._path(key)

    def _adopt(self, key: str, data: dict) -> None:
        sesion = session_from_dict(data)
        with self._guard:
            self._sessions[key] = sesion

    def get(self, session_id: SessionId) -> ClassroomSession | None:

        self._refresh(session_id.value)
        return super().get(session_id)

    def _refresh_directory(self) -> None:
        for path in self._dir.glob("*.json"):
            self._refresh(path.stem)

    def list_active(self) -> list[ClassroomSession]:
        self._refresh_directory()
        return super().list_active()

    def find_by_access_key(self, key: str) -> ClassroomSession | None:
        self._refresh_directory()
        return super().find_by_access_key(key)

    def _restore(self) -> None:
        for path in sorted(self._dir.glob("*.json")):
            data = _read(path)
            if not data:
                continue
            try:
                session = session_from_dict(data)
            except Exception:
                logger.exception("Sesion ilegible en %s; se ignora.", path)
                continue
            self._sessions[session.session_id.value] = session
        if self._sessions:
            logger.info("Restauradas %d sesiones desde disco.", len(self._sessions))

    def _persist(self, session: ClassroomSession) -> None:
        clave = session.session_id.value
        with self._io_lock:
            _atomic_write(self._path(clave), session_to_dict(session))

            self._mark_written(clave)

    def _forget(self, session_id: SessionId) -> None:
        with self._io_lock:
            path = self._path(session_id.value)
            if path.is_file():
                path.unlink()

class FileNotesRepository(InMemoryNotesRepository, _CrossProcessReload):
    def __init__(
        self,
        data_dir: Path | str,
        *,
        slide_tag_template: str | None = None,
        clarification_tag_template: str | None = None,
    ) -> None:
        super().__init__(
            slide_tag_template=slide_tag_template,
            clarification_tag_template=clarification_tag_template,
        )
        self._dir = Path(data_dir) / "notes"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._io_lock = threading.Lock()
        self._seen: dict[str, int] = {}
        self._restore()

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _watched_path(self, key: str) -> Path:
        return self._path(key)

    def _adopt(self, key: str, data: dict) -> None:
        with self._guard:
            self._notes[key] = notes_from_dict(data)

    def get(self, session_id: SessionId) -> StudentNotes | None:

        self._refresh(session_id.value)
        return super().get(session_id)

    def get_or_create(self, session_id: SessionId) -> StudentNotes:
        self._refresh(session_id.value)
        return super().get_or_create(session_id)

    def _restore(self) -> None:
        for path in sorted(self._dir.glob("*.json")):
            data = _read(path)
            if not data:
                continue
            try:
                notes = notes_from_dict(data)
            except Exception:
                logger.exception("Apuntes ilegibles en %s; se ignoran.", path)
                continue
            self._notes[notes.session_id.value] = notes

    def _persist(self, notes: StudentNotes) -> None:
        clave = notes.session_id.value
        with self._io_lock:
            _atomic_write(self._path(clave), notes_to_dict(notes))
            self._mark_written(clave)

class FileClarificationRepository(InMemoryClarificationRepository):

    _INTERVALO_RELECTURA = 0.15

    def __init__(self, data_dir: Path | str) -> None:
        super().__init__()
        self._dir = Path(data_dir) / "clarifications"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._io_lock = threading.Lock()
        self._conocidos: set[str] = set()
        self._ultima_lectura = 0.0
        self._restore()

    def _path(self, clarification_id: str) -> Path:
        return self._dir / f"{clarification_id}.json"

    def _refresh_directorio(self) -> None:

        import time as _time

        ahora = _time.monotonic()
        if (ahora - self._ultima_lectura) < self._INTERVALO_RELECTURA:
            return
        self._ultima_lectura = ahora

        nuevas: list[Clarification] = []
        for path in self._dir.glob("*.json"):
            clave = path.stem
            marca = _mtime(path)
            firma = f"{clave}:{marca}"
            if firma in self._conocidos:
                continue
            data = _read(path)
            if not data:
                continue
            try:
                nuevas.append(clarification_from_dict(data))
            except Exception:
                logger.exception("Aclaracion ilegible en %s; se ignora.", path)
                continue
            self._conocidos.add(firma)

        if not nuevas:
            return
        nuevas.sort(key=lambda c: (c.requested_at or c.completed_at or datetime.min))
        with self._guard:
            for clarification in nuevas:
                clave = clarification.clarification_id.value
                if clave not in self._by_id:
                    self._by_session[clarification.session_id.value].append(clave)
                self._by_id[clave] = clarification

    def get(self, clarification_id: ClarificationId) -> Clarification | None:
        self._refresh_directorio()
        return super().get(clarification_id)

    def latest_for_session(self, session_id: SessionId) -> Clarification | None:
        self._refresh_directorio()
        return super().latest_for_session(session_id)

    def list_for_session(self, session_id: SessionId, *, limit: int = 50) -> list[Clarification]:
        self._refresh_directorio()
        return super().list_for_session(session_id, limit=limit)

    def delete_for_session(self, session_id: SessionId) -> None:
        self._refresh_directorio()
        with self._guard:
            keys = self._by_session.pop(session_id.value, [])
            for key in keys:
                self._by_id.pop(key, None)
        with self._io_lock:
            for path in self._dir.glob("*.json"):
                data = _read(path)
                if data and data.get("session_id") == session_id.value:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
        self._conocidos = {
            signature
            for signature in self._conocidos
            if signature.split(":", 1)[0] in self._by_id
        }

    def _restore(self) -> None:
        loaded: list[Clarification] = []
        for path in sorted(self._dir.glob("*.json")):
            data = _read(path)
            if not data:
                continue
            try:
                loaded.append(clarification_from_dict(data))
            except Exception:
                logger.exception("Aclaracion ilegible en %s; se ignora.", path)

        loaded.sort(key=lambda c: c.requested_at or c.completed_at or 0)
        for clarification in loaded:
            key = clarification.clarification_id.value
            self._by_id[key] = clarification
            self._by_session[clarification.session_id.value].append(key)

    def _persist(self, clarification: Clarification) -> None:
        clave = clarification.clarification_id.value
        path = self._path(clave)
        with self._io_lock:
            _atomic_write(path, clarification_to_dict(clarification))
            marca = _mtime(path)
            if marca is not None:
                self._conocidos.add(f"{clave}:{marca}")
