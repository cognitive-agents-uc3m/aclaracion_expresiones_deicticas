from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...dto import AudioChunk, SpeechOutput, TranscriptionResult

@runtime_checkable
class SpeechToTextPort(Protocol):
    name: str

    def transcribe(self, audio: AudioChunk, *, context_hint: str = "") -> TranscriptionResult:

        ...

    @property
    def is_available(self) -> bool:

        ...

@runtime_checkable
class TextToSpeechPort(Protocol):
    name: str

    def synthesize(self, text: str, *, voice: str = "") -> SpeechOutput:

        ...
