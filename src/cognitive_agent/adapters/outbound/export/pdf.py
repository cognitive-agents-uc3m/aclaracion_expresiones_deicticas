from __future__ import annotations

from datetime import datetime
from ....application.dto import ExportedNotes
from ....domain.entities.student_notes import StudentNotes
from .markdown import PROCESSED_DISCLAIMER, _slugify

_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842
_MARGIN = 50
_FONT = "helv"
_SIZE = 12
_LINE_HEIGHT = int(_SIZE * 1.35)

class PdfNotesExporter:
    fmt = "pdf"
    mime_type = "application/pdf"
    extension = "pdf"

    def export(
        self,
        notes: StudentNotes,
        *,
        title: str = "",
        processed_text: str | None = None,
    ) -> ExportedNotes:
        import fitz

        heading = title.strip() or "Apuntes de clase"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        raw = notes.render_raw() or "(sin apuntes)"

        body: list[str] = [heading, "", f"Exportado el {stamp}", ""]
        if processed_text is None:
            body.extend(raw.split("\n"))
            processed = False
        else:
            body.extend(PROCESSED_DISCLAIMER.split("\n"))
            body.extend(["", *processed_text.strip().split("\n")])
            body.extend(["", "=" * 55, "VERSIÓN ORIGINAL", "=" * 55, ""])
            body.extend(raw.split("\n"))
            processed = True

        document = fitz.open()
        max_width = _PAGE_WIDTH - (2 * _MARGIN)
        wrapped: list[str] = []
        for line in body:
            wrapped.extend(_wrap(fitz, line, max_width))

        page = document.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
        y = _MARGIN + _SIZE
        for line in wrapped:
            if y + _LINE_HEIGHT > (_PAGE_HEIGHT - _MARGIN):
                page = document.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
                y = _MARGIN + _SIZE
            if line:
                page.insert_text(
                    (_MARGIN, y), line, fontsize=_SIZE, fontname=_FONT, color=(0, 0, 0)
                )
            y += _LINE_HEIGHT

        content = document.tobytes(deflate=True)
        document.close()

        filename = f"{_slugify(heading)}_{datetime.now().strftime('%Y-%m-%d-%H-%M')}.{self.extension}"
        return ExportedNotes(
            content=content,
            filename=filename,
            mime_type=self.mime_type,
            processed=processed,
            disclaimer=PROCESSED_DISCLAIMER if processed else "",
        )

_LATIN1_SUBSTITUTIONS = {
    "—": "-",
    "–": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "•": "-",
    " ": " ",
}

def _to_latin1(text: str) -> str:
    for source, target in _LATIN1_SUBSTITUTIONS.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "replace").decode("latin-1")

def _wrap(fitz, line: str, max_width: float) -> list[str]:
    text = _to_latin1((line or "").rstrip())
    if not text:
        return [""]

    out: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip() if current else word
        if fitz.get_text_length(candidate, fontname=_FONT, fontsize=_SIZE) <= max_width:
            current = candidate
            continue
        if current:
            out.append(current)
            current = ""
        if fitz.get_text_length(word, fontname=_FONT, fontsize=_SIZE) <= max_width:
            current = word
            continue
        chunk = ""
        for char in word:
            candidate_chunk = f"{chunk}{char}"
            if chunk and fitz.get_text_length(
                candidate_chunk, fontname=_FONT, fontsize=_SIZE
            ) > max_width:
                out.append(chunk)
                chunk = char
            else:
                chunk = candidate_chunk
        if chunk:
            current = chunk
    if current:
        out.append(current)
    return out
