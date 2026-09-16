from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class DeicticKind(str, Enum):

    PLACE = "place"
    DEMONSTRATIVE = "demonstrative"
    PERCEPTION = "perception"
    SPATIAL = "spatial"
    VISUAL_OBJECT = "visual_object"

    @property
    def display_name(self) -> str:
        return {
            DeicticKind.PLACE: "referencia de lugar",
            DeicticKind.DEMONSTRATIVE: "demostrativo",
            DeicticKind.PERCEPTION: "apelacion visual",
            DeicticKind.SPATIAL: "referencia espacial",
            DeicticKind.VISUAL_OBJECT: "objeto visual",
        }[self]

@dataclass(frozen=True, slots=True)
class DeicticExpression:

    surface: str
    kind: DeicticKind
    start: int
    end: int
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"Rango invalido para la expresion deictica: [{self.start}, {self.end})")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"La confianza debe estar entre 0 y 1: {self.confidence}")

    def __str__(self) -> str:
        return self.surface

@dataclass(frozen=True, slots=True)
class DeicticDetection:

    expressions: tuple[DeicticExpression, ...] = ()
    suppressed_by: str | None = None

    detector: str = "rules"
    decision_probability: float | None = None
    decision_threshold: float | None = None

    @property
    def detected(self) -> bool:
        return bool(self.expressions)

    @property
    def primary(self) -> DeicticExpression | None:

        if not self.expressions:
            return None
        return max(self.expressions, key=lambda e: (e.confidence, -e.start))

    @property
    def max_confidence(self) -> float:
        return max((e.confidence for e in self.expressions), default=0.0)

    @staticmethod
    def none(
        reason: str | None = None,
        detector: str = "rules",
        *,
        decision_probability: float | None = None,
        decision_threshold: float | None = None,
    ) -> "DeicticDetection":
        return DeicticDetection(
            expressions=(),
            suppressed_by=reason,
            detector=detector,
            decision_probability=decision_probability,
            decision_threshold=decision_threshold,
        )
