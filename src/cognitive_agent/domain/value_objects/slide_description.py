from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .identifiers import SlideIdentifier

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

class DescriptionFormat(str, Enum):
    TEXT = "text"
    HTML = "html"
    MARKDOWN = "markdown"

class DescriptionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class SlideDescription:

    slide: SlideIdentifier
    content: str
    summary: str = ""
    fmt: DescriptionFormat = DescriptionFormat.TEXT
    status: DescriptionStatus = DescriptionStatus.READY
    prompt_version: str = ""
    model: str = ""
    generated_at: datetime | None = None
    error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status is DescriptionStatus.READY and bool(self.content.strip())

    def as_plain_text(self) -> str:

        if self.fmt is not DescriptionFormat.HTML:
            return _WS.sub(" ", self.content).strip()
        text = _TAG.sub(" ", self.content)
        return _WS.sub(" ", html_lib.unescape(text)).strip()

    def excerpt(self, max_chars: int = 4000) -> str:

        text = self.as_plain_text()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rsplit(" ", 1)[0] + " [...]"

    @staticmethod
    def unavailable(slide: SlideIdentifier, reason: str = "") -> "SlideDescription":
        return SlideDescription(
            slide=slide,
            content="",
            status=DescriptionStatus.PENDING,
            error=reason or None,
        )
