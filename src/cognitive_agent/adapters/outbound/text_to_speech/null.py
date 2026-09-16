from __future__ import annotations

from ....application.dto import SpeechOutput

class NullTextToSpeech:
    name = "null"

    def synthesize(self, text: str, *, voice: str = "") -> SpeechOutput:
        return SpeechOutput(text=(text or "").strip(), audio=b"", mime_type="", provider=self.name)
