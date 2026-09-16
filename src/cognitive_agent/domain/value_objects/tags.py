from __future__ import annotations

import re
from dataclasses import dataclass
from .identifiers import SlideIdentifier

DEFAULT_SLIDE_TAG_TEMPLATE = "[Diapositiva {number}]"

DEFAULT_CLARIFICATION_TAG_TEMPLATE = "[Aclaración — Diapositiva {number}]"

SLIDE_TAG_PATTERN = re.compile(r"\[Diapositiva\s+(\d+)\]")
CLARIFICATION_TAG_PATTERN = re.compile(r"\[Aclaraci[oó]n(?:\s*[-—:]\s*Diapositiva\s+(\d+))?[^\]]*\]")

@dataclass(frozen=True, slots=True)
class SlideTag:

    slide: SlideIdentifier
    template: str = DEFAULT_SLIDE_TAG_TEMPLATE

    def render(self) -> str:
        return self.template.format(number=self.slide.number, index=self.slide.index)

    @property
    def accessible_label(self) -> str:

        return f"Diapositiva {self.slide.number}"

@dataclass(frozen=True, slots=True)
class ClarificationTag:

    slide: SlideIdentifier
    text: str
    template: str = DEFAULT_CLARIFICATION_TAG_TEMPLATE

    def render(self) -> str:
        header = self.template.format(number=self.slide.number, index=self.slide.index)
        body = " ".join(self.text.split()).strip()
        if not body:
            return header
        if not body.endswith((".", "!", "?", ":")):
            body += "."
        return f"{header} {body}"

    @property
    def accessible_label(self) -> str:
        return f"Aclaracion de la diapositiva {self.slide.number}"
