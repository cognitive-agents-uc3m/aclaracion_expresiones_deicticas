from __future__ import annotations

from datetime import datetime
from ....application.dto import ExportedNotes
from ....domain.entities.student_notes import StudentNotes
from .markdown import PROCESSED_DISCLAIMER, _slugify

class PlainTextNotesExporter:
    fmt = "text"
    mime_type = "text/plain; charset=utf-8"
    extension = "txt"

    def export(
        self,
        notes: StudentNotes,
        *,
        title: str = "",
        processed_text: str | None = None,
    ) -> ExportedNotes:
        heading = title.strip() or "Apuntes de clase"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        raw = notes.render_raw() or "(sin apuntes)"

        lines = [heading, "=" * len(heading), f"Exportado el {stamp}", ""]
        if processed_text is None:
            lines.append(raw)
            processed = False
        else:
            lines.extend([PROCESSED_DISCLAIMER, "", processed_text.strip(), ""])
            lines.extend(
                ["", "-" * 60, "VERSIÓN ORIGINAL", "-" * 60, "", raw]
            )
            processed = True

        content = "\n".join(lines).rstrip() + "\n"
        filename = f"{_slugify(heading)}_{datetime.now().strftime('%Y-%m-%d-%H-%M')}.{self.extension}"
        return ExportedNotes(
            content=content.encode("utf-8"),
            filename=filename,
            mime_type=self.mime_type,
            processed=processed,
            disclaimer=PROCESSED_DISCLAIMER if processed else "",
        )
