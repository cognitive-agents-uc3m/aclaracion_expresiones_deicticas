from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .identifiers import SlideIdentifier

@dataclass(frozen=True, slots=True)
class PointerPosition:
    x: float
    y: float
    at: datetime
    slide: SlideIdentifier

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            raise ValueError(f"Coordenadas fuera de la diapositiva: ({self.x}, {self.y})")

    def is_fresh(self, *, now: datetime, max_age: timedelta) -> bool:

        return (now - self.at) <= max_age

    def applies_to(self, slide: SlideIdentifier | None) -> bool:
        return slide is not None and slide == self.slide
