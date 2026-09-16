from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from ....domain.value_objects.identifiers import DeckId, SlideIdentifier
from ....domain.value_objects.slide_description import (
    DescriptionFormat,
    DescriptionStatus,
    SlideDescription,
)

logger = logging.getLogger(__name__)

KNOWLEDGE_VERSION = 1

_STATUS_FROM_DB = {
    "ready": DescriptionStatus.READY,
    "processing": DescriptionStatus.PROCESSING,
    "error": DescriptionStatus.FAILED,
    "pending": DescriptionStatus.PENDING,
}
_STATUS_TO_DB = {v: k for k, v in _STATUS_FROM_DB.items()}

def _guess_format(content: str) -> DescriptionFormat:

    head = (content or "").lstrip()[:200].lower()
    if head.startswith("<") or "<section" in head or "<h2" in head:
        return DescriptionFormat.HTML
    return DescriptionFormat.TEXT

class SqliteSlideDescriptionRepository:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._schema_lock = threading.Lock()
        self._ensure_schema()

    def _connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self._db_path, timeout=30)
            connection.row_factory = sqlite3.Row
            with connection:
                connection.execute("PRAGMA journal_mode=WAL;")
                connection.execute("PRAGMA synchronous=NORMAL;")
                connection.execute("PRAGMA foreign_keys=ON;")
            self._local.connection = connection
        return connection

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    def _ensure_schema(self) -> None:
        with self._schema_lock:
            connection = self._connection()
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS presentations (
                        deck_id TEXT PRIMARY KEY,
                        pdf_path TEXT NOT NULL DEFAULT '',
                        file_hash TEXT NOT NULL DEFAULT '',
                        file_size INTEGER NOT NULL DEFAULT 0,
                        file_mtime INTEGER NOT NULL DEFAULT 0,
                        slide_count INTEGER NOT NULL DEFAULT 0,
                        knowledge_version INTEGER NOT NULL DEFAULT 1,
                        created_at REAL NOT NULL DEFAULT 0,
                        updated_at REAL NOT NULL DEFAULT 0
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS slides (
                        deck_id TEXT NOT NULL,
                        slide_index INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        detailed_description TEXT,
                        summary TEXT,
                        spatial_mentions TEXT,
                        elements_json TEXT,
                        error TEXT,
                        vision_model TEXT,
                        knowledge_version INTEGER NOT NULL DEFAULT 1,
                        updated_at REAL NOT NULL DEFAULT 0,
                        PRIMARY KEY (deck_id, slide_index)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_slides_status ON slides(deck_id, status)"
                )
                columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(slides)").fetchall()
                }

                for column, ddl in (
                    ("elements_json", "ALTER TABLE slides ADD COLUMN elements_json TEXT"),
                    (
                        "description_format",
                        "ALTER TABLE slides ADD COLUMN description_format TEXT",
                    ),
                    ("prompt_version", "ALTER TABLE slides ADD COLUMN prompt_version TEXT"),
                ):
                    if column not in columns:
                        connection.execute(ddl)
                        logger.info("Esquema de diapositivas ampliado con la columna %s.", column)

    def get(self, slide: SlideIdentifier) -> SlideDescription | None:
        row = (
            self._connection()
            .execute(
                """
                SELECT status, detailed_description, summary, error, vision_model,
                       description_format, prompt_version, updated_at
                FROM slides WHERE deck_id = ? AND slide_index = ?
                """,
                (slide.deck_id.value, int(slide.index)),
            )
            .fetchone()
        )
        if row is None:
            return None

        content = row["detailed_description"] or ""
        raw_format = row["description_format"]
        fmt = (
            DescriptionFormat(raw_format)
            if raw_format in {f.value for f in DescriptionFormat}
            else _guess_format(content)
        )
        return SlideDescription(
            slide=slide,
            content=content,
            summary=row["summary"] or "",
            fmt=fmt,
            status=_STATUS_FROM_DB.get(row["status"], DescriptionStatus.PENDING),
            prompt_version=row["prompt_version"] or "",
            model=row["vision_model"] or "",
            error=row["error"],
        )

    def save(self, description: SlideDescription) -> None:

        connection = self._connection()
        now = time.time()
        deck_id = description.slide.deck_id.value
        with connection:
            connection.execute(
                """
                INSERT INTO presentations (
                    deck_id, pdf_path, file_hash, file_size, file_mtime,
                    slide_count, knowledge_version, created_at, updated_at
                ) VALUES (?, '', '', 0, 0, 0, ?, ?, ?)
                ON CONFLICT(deck_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (deck_id, KNOWLEDGE_VERSION, now, now),
            )
            connection.execute(
                """
                INSERT INTO slides (
                    deck_id, slide_index, status, detailed_description, summary,
                    error, vision_model, description_format, prompt_version,
                    knowledge_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_id, slide_index) DO UPDATE SET
                    status=excluded.status,
                    detailed_description=excluded.detailed_description,
                    summary=excluded.summary,
                    error=excluded.error,
                    vision_model=excluded.vision_model,
                    description_format=excluded.description_format,
                    prompt_version=excluded.prompt_version,
                    updated_at=excluded.updated_at
                """,
                (
                    deck_id,
                    int(description.slide.index),
                    _STATUS_TO_DB.get(description.status, "pending"),
                    description.content,
                    description.summary,
                    description.error,
                    description.model,
                    description.fmt.value,
                    description.prompt_version,
                    KNOWLEDGE_VERSION,
                    now,
                ),
            )

    def register_deck(self, deck_id: str, slide_count: int, *, pdf_path: str = "") -> None:
        connection = self._connection()
        now = time.time()
        with connection:
            connection.execute(
                """
                INSERT INTO presentations (
                    deck_id, pdf_path, file_hash, file_size, file_mtime,
                    slide_count, knowledge_version, created_at, updated_at
                ) VALUES (?, ?, '', 0, 0, ?, ?, ?, ?)
                ON CONFLICT(deck_id) DO UPDATE SET
                    pdf_path=excluded.pdf_path,
                    slide_count=excluded.slide_count,
                    updated_at=excluded.updated_at
                """,
                (deck_id, pdf_path, int(slide_count), KNOWLEDGE_VERSION, now, now),
            )

    def deck_progress(self, deck_id: str) -> tuple[int, int, int, int]:
        connection = self._connection()
        deck_row = connection.execute(
            "SELECT slide_count FROM presentations WHERE deck_id = ?", (deck_id,)
        ).fetchone()
        total = int(deck_row["slide_count"]) if deck_row else 0

        ready = failed = processing = 0
        for row in connection.execute(
            "SELECT status, COUNT(*) AS c FROM slides WHERE deck_id = ? GROUP BY status",
            (deck_id,),
        ):
            count = int(row["c"])
            if row["status"] == "ready":
                ready += count
            elif row["status"] == "error":
                failed += count
            elif row["status"] == "processing":
                processing += count

        if total == 0:
            total = ready + failed + processing
        return ready, total, failed, processing

    def pending_slides(self, deck_id: str, slide_count: int) -> list[int]:
        done = {
            int(row["slide_index"])
            for row in self._connection().execute(
                "SELECT slide_index FROM slides WHERE deck_id = ? AND status = 'ready'",
                (deck_id,),
            )
        }
        return [index for index in range(slide_count) if index not in done]

    def known_decks(self) -> list[tuple[str, int]]:
        return [
            (row["deck_id"], int(row["slide_count"]))
            for row in self._connection().execute(
                "SELECT deck_id, slide_count FROM presentations ORDER BY updated_at DESC"
            )
        ]

    def slide_of(self, deck_id: str, index: int) -> SlideIdentifier:
        return SlideIdentifier(DeckId(deck_id), index)
