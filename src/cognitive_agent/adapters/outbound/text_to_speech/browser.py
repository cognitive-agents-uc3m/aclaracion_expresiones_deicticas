from __future__ import annotations

from ....application.dto import SpeechOutput

class BrowserTextToSpeech:

    name = "browser"

    def __init__(self, *, language: str = "es-ES") -> None:
        self._language = language

    def synthesize(self, text: str, *, voice: str = "") -> SpeechOutput:
        clean = (text or "").strip()
        return SpeechOutput(text=clean, audio=b"", mime_type="", provider=self.name)

    @property
    def language(self) -> str:
        return self._language
