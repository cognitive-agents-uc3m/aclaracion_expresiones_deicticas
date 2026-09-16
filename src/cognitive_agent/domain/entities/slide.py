from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidSlideIndex
from ..value_objects.identifiers import DeckId, SlideIdentifier
from ..value_objects.slide_description import SlideDescription

@dataclass(frozen=True, slots=True)
class Deck:

    deck_id: DeckId
    slide_count: int
    title: str = ""
    source_name: str = ""

    def __post_init__(self) -> None:
        if self.slide_count < 0:
            raise InvalidSlideIndex(f"Un mazo no puede tener {self.slide_count} diapositivas.")

    @property
    def is_empty(self) -> bool:
        return self.slide_count == 0

    def slide_at(self, index: int) -> SlideIdentifier:
        if not 0 <= index < self.slide_count:
            raise InvalidSlideIndex(
                f"La diapositiva {index + 1} no existe: el mazo tiene {self.slide_count}."
            )
        return SlideIdentifier(self.deck_id, index)

    def clamp(self, index: int) -> int:

        if self.slide_count <= 0:
            return 0
        return max(0, min(int(index), self.slide_count - 1))

    def contains(self, slide: SlideIdentifier) -> bool:
        return slide.deck_id == self.deck_id and 0 <= slide.index < self.slide_count

@dataclass(frozen=True, slots=True)
class Slide:

    identifier: SlideIdentifier
    description: SlideDescription | None = None

    @property
    def number(self) -> int:
        return self.identifier.number

    @property
    def has_accessible_description(self) -> bool:
        return self.description is not None and self.description.is_ready
