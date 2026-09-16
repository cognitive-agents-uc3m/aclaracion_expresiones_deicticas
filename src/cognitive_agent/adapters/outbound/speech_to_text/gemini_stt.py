from __future__ import annotations

import logging
import time

from ....application.dto import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)

_MIME_BY_EXTENSION = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}

class GeminiSpeechToText:
    name = "gemini"

    def __init__(
        self,
        *,
        model_id: str = "gemini-2.5-flash",
        project: str = "",
        location: str = "us-central1",
        prompts=None,
        language: str = "es",
        disable_thinking: bool = True,
    ) -> None:
        self.model_id = model_id
        self._project = project
        self._location = location
        self._prompts = prompts
        self._language = language
        self._disable_thinking = disable_thinking
        self._client = None
        self._instruction: str | None = None

    def _system_instruction(self) -> str:
        if self._instruction is not None:
            return self._instruction
        if self._prompts is not None:
            try:
                rendered = self._prompts.render("transcription")
                self._instruction = rendered.system or rendered.user
                return self._instruction
            except Exception:
                logger.debug("No se pudo cargar el prompt de transcripcion; se usa el interno.")
        self._instruction = (
            "Eres un sistema de transcripcion de voz a texto (STT). Transcribe "
            "literalmente el audio, que esta en espanol. Devuelve UNICAMENTE el texto "
            "transcrito, sin comillas, sin puntuacion inventada de mas y sin comentarios "
            "ni explicaciones. Si el audio no contiene habla inteligible, devuelve una "
            "cadena vacia."
        )
        return self._instruction

    def _get_client(self):
        if self._client is not None:
            return self._client
        from google import genai

        from ..llm.gemini import resolve_gcp_location, resolve_gcp_project

        project = resolve_gcp_project(self._project)
        if not project:
            raise RuntimeError("No hay proyecto de GCP configurado para la transcripcion.")
        self._client = genai.Client(
            vertexai=True, project=project, location=resolve_gcp_location(self._location)
        )
        return self._client

    def transcribe(self, audio: AudioChunk, *, context_hint: str = "") -> TranscriptionResult:
        if audio.is_empty:
            return TranscriptionResult(text="", provider=self.name, model=self.model_id)

        started = time.monotonic()
        try:
            from google.genai import types

            client = self._get_client()
            parts = []
            if context_hint:
                parts.append(
                    types.Part.from_text(
                        text=f"Contexto de la clase (terminos que pueden aparecer): {context_hint}"
                    )
                )
            parts.append(
                types.Part.from_bytes(data=audio.data, mime_type=audio.mime_type or "audio/wav")
            )

            config_kwargs: dict = {
                "system_instruction": self._system_instruction(),
                "temperature": 0,
            }
            if self._disable_thinking and "flash" in self.model_id.lower():
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

            response = client.models.generate_content(
                model=self.model_id,
                contents=parts,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = (getattr(response, "text", "") or "").strip()
        except Exception as exc:
            logger.error("Error transcribiendo con Gemini: %s: %s", type(exc).__name__, exc)
            return TranscriptionResult(text="", provider=self.name, model=self.model_id)

        return TranscriptionResult(
            text=text,
            provider=self.name,
            model=self.model_id,
            latency_ms=int((time.monotonic() - started) * 1000),
            language=self._language,
        )

    @property
    def is_available(self) -> bool:
        try:
            self._get_client()
        except Exception:
            return False
        return True

    @staticmethod
    def mime_for(filename: str) -> str:
        import os

        return _MIME_BY_EXTENSION.get(os.path.splitext(filename)[1].lower(), "audio/wav")
