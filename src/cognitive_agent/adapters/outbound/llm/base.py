from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True, slots=True)
class ChatResponse:
    text: str
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

@runtime_checkable
class ChatModel(Protocol):

    name: str
    model_id: str

    def complete(
        self,
        *,
        system: str = "",
        user: str = "",
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> ChatResponse: ...

    @property
    def is_available(self) -> bool: ...

@runtime_checkable
class VisionModel(Protocol):

    name: str
    model_id: str

    def describe(
        self,
        *,
        prompt: str,
        image: bytes | None = None,
        pdf: bytes | None = None,
        mime_type: str = "image/png",
        timeout_seconds: float | None = None,
    ) -> ChatResponse: ...

    @property
    def is_available(self) -> bool: ...

class LlmUnavailable(RuntimeError):
    pass
