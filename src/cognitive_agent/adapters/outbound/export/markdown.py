from __future__ import annotations

from collections import OrderedDict
from datetime import datetime

from ....application.dto import ExportedNotes
from ....domain.entities.note_entry import (
    ClarificationNoteEntry,
    NoteEntryKind,
    SlideTagNoteEntry,
    TextNoteEntry,
)
from ....domain.entities.student_notes import StudentNotes

PROCESSED_DISCLAIMER = (
    "Este documento ha sido reorganizado automáticamente para facilitar su lectura. "
    "El texto original que escribiste se conserva íntegro y sin modificar en el "
    "apartado final 'Versión original'."
)

def _slugify(text: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_")
    return (slug[:60] or "apuntes").lower()

class MarkdownNotesExporter:
    fmt = "markdown"
    mime_type = "text/markdown; charset=utf-8"
    extension = "md"

    def export(
        self,
        notes: StudentNotes,
        *,
        title: str = "",
        processed_text: str | None = None,
    ) -> ExportedNotes:
        heading = title.strip() or "Apuntes de clase"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines: list[str] = [f"# {heading}", "", f"_Exportado el {stamp}_", ""]

        if processed_text is None:
            lines.extend(self._raw_body(notes))
            processed = False
        else:
            lines.append(f"> {PROCESSED_DISCLAIMER}")
            lines.append("")
            lines.extend(self._grouped_body(notes, processed_text))
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Versión original")
            lines.append("")
            lines.append("```text")
            lines.append(notes.render_raw() or "(sin apuntes)")
            lines.append("```")
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

    @staticmethod
    def _raw_body(notes: StudentNotes) -> list[str]:
        if notes.is_empty:
            return ["_No hay apuntes para esta sesion._"]

        lines: list[str] = []
        for entry in notes.entries:
            if isinstance(entry, SlideTagNoteEntry) and entry.slide is not None:
                lines.extend(["", f"## Diapositiva {entry.slide.number}", ""])
            elif isinstance(entry, ClarificationNoteEntry) and entry.tag is not None:
                lines.extend(
                    ["", f"> **Aclaracion (diapositiva {entry.slide.number if entry.slide else '?'})**: "
                     f"{entry.tag.text}", ""]
                )
            elif isinstance(entry, TextNoteEntry) and entry.text.strip():
                lines.append(entry.text)
        return lines

    @staticmethod
    def _grouped_body(notes: StudentNotes, processed_text: str) -> list[str]:

        groups: OrderedDict[int, list[str]] = OrderedDict()
        visits: dict[int, int] = {}
        clarifications: OrderedDict[int, list[str]] = OrderedDict()
        current: int | None = None

        for entry in notes.entries:
            if entry.kind is NoteEntryKind.SLIDE_TAG and entry.slide is not None:
                current = entry.slide.number
                groups.setdefault(current, [])
                visits[current] = visits.get(current, 0) + 1
            elif isinstance(entry, ClarificationNoteEntry) and entry.tag is not None:
                key = entry.slide.number if entry.slide else (current or 0)
                clarifications.setdefault(key, []).append(entry.tag.text)
            elif isinstance(entry, TextNoteEntry) and entry.text.strip():
                groups.setdefault(current or 0, []).append(entry.text.strip())

        lines: list[str] = ["## Contenido reorganizado", ""]
        if not groups and not clarifications:
            lines.append("_No hay apuntes para esta sesion._")
            return lines

        for number in sorted(set(groups) | set(clarifications)):
            label = "Sin diapositiva" if number == 0 else f"Diapositiva {number}"
            times = visits.get(number, 0)
            suffix = f" _(visitada {times} veces)_" if times > 1 else ""
            lines.extend([f"### {label}{suffix}", ""])
            for block in groups.get(number, []):
                lines.extend([block, ""])
            for text in clarifications.get(number, []):
                lines.extend([f"> **Aclaracion**: {text}", ""])

        lines.extend(["", "## Texto revisado", "", processed_text.strip(), ""])
        return lines
