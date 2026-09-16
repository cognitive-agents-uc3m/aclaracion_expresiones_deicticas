from __future__ import annotations

import logging

from ....application.dto import SpeechOutput

logger = logging.getLogger(__name__)

class LocalTextToSpeech:
    name = "pyttsx3"

    def __init__(self, *, rate: int = 175) -> None:
        self._rate = rate

    def synthesize(self, text: str, *, voice: str = "") -> SpeechOutput:
        clean = (text or "").strip()
        if not clean:
            return SpeechOutput(text="", provider=self.name)

        try:
            import os
            import tempfile
            import uuid
            import pyttsx3

            out_dir = os.path.join(tempfile.gettempdir(), "cognitive_agent_tts")
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"tts_{uuid.uuid4().hex}.wav")

            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            if voice:
                engine.setProperty("voice", voice)
            engine.save_to_file(clean, out_path)
            engine.runAndWait()

            if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                with open(out_path, "rb") as handle:
                    audio = handle.read()
                os.unlink(out_path)
                return SpeechOutput(
                    text=clean, audio=audio, mime_type="audio/wav", provider=self.name
                )
        except Exception as exc:
            logger.warning("pyttsx3 no disponible (%s); se delega en el cliente.", exc)

        return SpeechOutput(text=clean, audio=b"", mime_type="", provider="browser")
