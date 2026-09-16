from __future__ import annotations

from ....application.dto import AudioChunk, TranscriptionResult

class FakeSpeechToText:
    name = "fake"

    def __init__(self, *, text: str = "Aqui podemos ver esta grafica de barras") -> None:
        self._text = text
        self.calls: list[tuple[int, str]] = []

    def transcribe(self, audio: AudioChunk, *, context_hint: str = "") -> TranscriptionResult:
        self.calls.append((len(audio.data), context_hint))
        if audio.is_empty:
            return TranscriptionResult(text="", provider=self.name)
        return TranscriptionResult(
            text=self._text, provider=self.name, model="fake-stt", latency_ms=5
        )

    @property
    def is_available(self) -> bool:
        return True

class ScriptedSpeechToText:

    name = "scripted"

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self._index = 0
        self.calls: list[str] = []

    def transcribe(self, audio: AudioChunk, *, context_hint: str = "") -> TranscriptionResult:
        self.calls.append(context_hint)

        if audio.is_empty or self._index >= len(self._lines):
            return TranscriptionResult(text="", provider=self.name)
        text = self._lines[self._index]
        self._index += 1
        return TranscriptionResult(text=text, provider=self.name, model="scripted")

    @property
    def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        self._index = 0
        self.calls.clear()
