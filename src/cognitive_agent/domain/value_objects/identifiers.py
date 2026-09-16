from __future__ import annotations

import uuid
from dataclasses import dataclass

from ..errors import InvalidSlideIndex

@dataclass(frozen=True, slots=True, order=True)
class SessionId:
    value: str

    @staticmethod
    def new() -> "SessionId":
        return SessionId(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value

@dataclass(frozen=True, slots=True, order=True)
class DeckId:

    value: str

    def __str__(self) -> str:
        return self.value

@dataclass(frozen=True, slots=True, order=True)
class SlideIdentifier:

    deck_id: DeckId
    index: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise InvalidSlideIndex(f"El indice de diapositiva no puede ser negativo: {self.index}")

    @property
    def number(self) -> int:

        return self.index + 1

    def with_index(self, index: int) -> "SlideIdentifier":
        return SlideIdentifier(self.deck_id, index)

    def __str__(self) -> str:
        return f"{self.deck_id.value}#{self.index}"

@dataclass(frozen=True, slots=True, order=True)
class ClarificationId:
    value: str

    @staticmethod
    def new() -> "ClarificationId":
        return ClarificationId(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value

@dataclass(frozen=True, slots=True, order=True)
class NoteEntryId:
    value: str

    @staticmethod
    def new() -> "NoteEntryId":
        return NoteEntryId(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value

@dataclass(frozen=True, slots=True, order=True)
class FragmentId:
    value: str

    @staticmethod
    def new() -> "FragmentId":
        return FragmentId(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value
