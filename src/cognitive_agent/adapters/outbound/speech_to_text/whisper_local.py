from __future__ import annotations

import io
import logging
import time
import wave

from ....application.dto import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)

class WhisperSpeechToText:
    name = "whisper_local"

    def __init__(
        self,
        *,
        model_size: str = "small",
        device: str = "cpu",
        language: str = "es",
        beam_size: int = 5,
        best_of: int = 5,
        no_speech_threshold: float = 0.45,
        condition_on_previous_text: bool = True,
        fp16: bool = False,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._language = language
        self._beam_size = beam_size
        self._best_of = best_of
        self._no_speech_threshold = no_speech_threshold
        self._condition_on_previous_text = condition_on_previous_text
        self._fp16 = fp16
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model
        import whisper

        device = self._device
        if device == "auto":
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        logger.info("Cargando Whisper %s en %s...", self._model_size, device)
        self._model = whisper.load_model(self._model_size, device=device)
        self._resolved_device = device
        return self._model

    def transcribe(self, audio: AudioChunk, *, context_hint: str = "") -> TranscriptionResult:
        if audio.is_empty:
            return TranscriptionResult(text="", provider=self.name)

        started = time.monotonic()
        try:
            import numpy as np

            model = self._get_model()
            samples = self._to_float32(audio, np)
            if samples is None:
                return TranscriptionResult(text="", provider=self.name)

            result = model.transcribe(
                samples,
                language=self._language,
                temperature=0,
                fp16=self._fp16 and getattr(self, "_resolved_device", "cpu") == "cuda",
                beam_size=self._beam_size,
                best_of=self._best_of,
                no_speech_threshold=self._no_speech_threshold,
                condition_on_previous_text=self._condition_on_previous_text,
                initial_prompt=context_hint or None,
            )
            text = (result.get("text") or "").strip()
        except Exception as exc:
            logger.error("Error transcribiendo con Whisper: %s: %s", type(exc).__name__, exc)
            return TranscriptionResult(text="", provider=self.name)

        return TranscriptionResult(
            text=text,
            provider=self.name,
            model=self._model_size,
            latency_ms=int((time.monotonic() - started) * 1000),
            language=self._language,
        )

    @staticmethod
    def _to_float32(audio: AudioChunk, np):

        if (audio.mime_type or "").endswith("wav") or audio.data[:4] == b"RIFF":
            with wave.open(io.BytesIO(audio.data), "rb") as handle:
                sample_rate = handle.getframerate()
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                frames = handle.readframes(handle.getnframes())
            if width != 2:
                return None
            samples = np.frombuffer(frames, dtype=np.int16)
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1)
            array = samples.astype(np.float32) / 32768.0
        else:
            return None

        if sample_rate != 16000 and array.size:
            target = max(1, int(round(array.shape[0] * 16000.0 / float(sample_rate))))
            array = np.interp(
                np.linspace(0.0, array.shape[0] - 1, target),
                np.arange(array.shape[0], dtype=np.float64),
                array.astype(np.float64),
            ).astype(np.float32)
        return np.clip(array, -1.0, 1.0)

    @property
    def is_available(self) -> bool:
        try:
            import whisper
        except ImportError:
            return False
        return True
