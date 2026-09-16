from __future__ import annotations

from typing import Protocol, runtime_checkable

from ....domain.value_objects.prompt import PromptRef, RenderedPrompt
from ....domain.value_objects.subject import Subject

@runtime_checkable
class PromptRepositoryPort(Protocol):
    def render(
        self,
        name: str,
        *,
        subject: Subject = Subject.GENERIC,
        variables: dict[str, str] | None = None,
        version: str | None = None,
    ) -> RenderedPrompt:

        ...

    def ref(self, name: str, *, subject: Subject = Subject.GENERIC, version: str | None = None) -> PromptRef: ...

    def available(self) -> dict[str, list[str]]:

        ...
