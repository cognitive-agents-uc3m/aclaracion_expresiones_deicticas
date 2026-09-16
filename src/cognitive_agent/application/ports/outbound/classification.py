from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ....domain.value_objects.subject import Subject

@dataclass(frozen=True, slots=True)
class DeicticClassification:
    needs_clarification: bool
    probability: float
    threshold: float
    model_version: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("La probabilidad debe estar entre 0 y 1.")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("El umbral debe estar entre 0 y 1.")

@runtime_checkable
class DeicticClassifierPort(Protocol):

    name: str

    def classify(
        self, text: str, *, subject: Subject = Subject.GENERIC
    ) -> DeicticClassification: ...

__all__ = ["DeicticClassification", "DeicticClassifierPort"]
