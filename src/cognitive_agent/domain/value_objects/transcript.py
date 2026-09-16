from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from .content_source import ContentSource
from .identifiers import FragmentId, SessionId, SlideIdentifier

_WHITESPACE = re.compile(r"\s+")

def normalize_text(text: str) -> str:

    return _WHITESPACE.sub(" ", (text or "").strip())

def fold_accents(text: str) -> str:

    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

@dataclass(frozen=True, slots=True)
class TranscriptFragment:

    text: str
    received_at: datetime
    session_id: SessionId
    slide: SlideIdentifier | None = None
    source: ContentSource = ContentSource.TEACHER
    fragment_id: FragmentId = field(default_factory=FragmentId.new)

    @property
    def normalized(self) -> str:
        return normalize_text(self.text)

    @property
    def is_empty(self) -> bool:
        return not self.normalized

    def bound_to(self, slide: SlideIdentifier | None) -> "TranscriptFragment":
        return TranscriptFragment(
            text=self.text,
            received_at=self.received_at,
            session_id=self.session_id,
            slide=slide,
            source=self.source,
            fragment_id=self.fragment_id,
        )

@dataclass(frozen=True, slots=True)
class TranscriptContext:

    fragments: tuple[TranscriptFragment, ...] = ()
    max_size: int = 3

    def __post_init__(self) -> None:
        if self.max_size < 1:
            raise ValueError("La ventana de contexto debe admitir al menos un fragmento.")

    def append(self, fragment: TranscriptFragment) -> "TranscriptContext":

        if fragment.is_empty:
            return self
        combined = (*self.fragments, fragment)[-self.max_size :]
        return TranscriptContext(fragments=combined, max_size=self.max_size)

    def resized(self, max_size: int) -> "TranscriptContext":
        return TranscriptContext(fragments=self.fragments[-max_size:], max_size=max_size)

    def cleared(self) -> "TranscriptContext":

        return TranscriptContext(fragments=(), max_size=self.max_size)

    @property
    def latest(self) -> TranscriptFragment | None:
        return self.fragments[-1] if self.fragments else None

    @property
    def is_empty(self) -> bool:
        return not self.fragments

    def as_text(self) -> str:
        return " ".join(f.normalized for f in self.fragments if f.normalized)

    def preceding_text(self) -> str:

        return " ".join(f.normalized for f in self.fragments[:-1] if f.normalized)

    def __len__(self) -> int:
        return len(self.fragments)
