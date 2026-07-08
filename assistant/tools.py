import logging
import os
import subprocess
from typing import Optional
from .settings import settings

logger = logging.getLogger(__name__)

def normalize_audio_mono_float32(audio_array):
    import numpy as np

    arr = np.asarray(audio_array)
    if arr.size == 0:
        return None
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    if np.issubdtype(arr.dtype, np.integer):
        max_int = np.iinfo(arr.dtype).max
        if max_int == 0:
            return None
        arr = arr.astype(np.float32) / float(max_int)
    else:
        arr = arr.astype(np.float32)
    return np.clip(arr, -1.0, 1.0)

class HardwareInterface:
    def __init__(self):
        self._whisper_model = None
        self._whisper_device: Optional[str] = None
        self._tts_engine = None

    def capture_audio_segment(self) -> str:
        import time
        from colorama import Fore, Style
        print(f"\n{Fore.GREEN}>> Input: {Style.RESET_ALL}", end="")
        try:
            user_input = input()
        except EOFError:
            return "."
        if not user_input.strip():
            time.sleep(0.5)
            return "."
        return user_input

    def _get_whisper_model(self):
        if self._whisper_model is not None:
            return self._whisper_model
        try:
            import whisper
            import torch

            requested_device = (settings.whisper_device or "auto").lower()
            cuda_available = torch.cuda.is_available()

            if requested_device == "auto":
                selected_device = "cuda" if cuda_available else "cpu"
            elif requested_device == "cuda":
                selected_device = "cuda"
                if not cuda_available:
                    raise RuntimeError(
                        "Se solicito CUDA para Whisper pero torch no tiene CUDA disponible. "
                        "Instala una build de PyTorch con CUDA y verifica torch.cuda.is_available()."
                    )
            elif requested_device == "cpu":
                selected_device = "cpu"
            else:
                raise RuntimeError(
                    f"Valor de whisper_device no valido: {requested_device!r}. Usa 'auto', 'cuda' o 'cpu'."
                )

            logger.info("[STT] Cargando Whisper (%s) en %s...", settings.whisper_model_size, selected_device)
            self._whisper_model = whisper.load_model(settings.whisper_model_size, device=selected_device)
            self._whisper_device = selected_device
            return self._whisper_model
        except Exception as ex:
            logger.error("[STT] Whisper no disponible: %s", ex)
            return None

    def _whisper_options(self, prompt_text: str) -> dict:
        return {
            "language": "es",
            "fp16": bool(settings.whisper_fp16 and self._whisper_device == "cuda"),
            "temperature": 0,
            "beam_size": settings.whisper_beam_size,
            "best_of": settings.whisper_best_of,
            "no_speech_threshold": settings.whisper_no_speech_threshold,
            "condition_on_previous_text": settings.whisper_condition_on_previous_text,
            "initial_prompt": prompt_text or None,
        }

    def transcribe_audio_file(self, audio_path: str, prompt_text: str = "") -> str:
        if not audio_path or not os.path.exists(audio_path):
            return ""

        model = self._get_whisper_model()
        if model is None:
            return ""

        try:
            result = model.transcribe(audio_path, **self._whisper_options(prompt_text))
            return (result.get("text") or "").strip()
        except Exception as ex:
            logger.error("[STT] Error transcribiendo audio: %s", ex)
            return ""

    def transcribe_audio_array(self, sample_rate: int, audio_array, prompt_text: str = "") -> str:
        if sample_rate is None or sample_rate <= 0 or audio_array is None:
            return ""

        model = self._get_whisper_model()
        if model is None:
            return ""

        try:
            import numpy as np

            arr = normalize_audio_mono_float32(audio_array)
            if arr is None:
                return ""
            if int(sample_rate) != 16000:
                target_len = max(1, int(round(arr.shape[0] * 16000.0 / float(sample_rate))))
                arr = np.interp(
                    np.linspace(0.0, arr.shape[0] - 1, target_len),
                    np.arange(arr.shape[0], dtype=np.float64),
                    arr.astype(np.float64),
                ).astype(np.float32)
            result = model.transcribe(arr, **self._whisper_options(prompt_text))
            return (result.get("text") or "").strip()
        except Exception as ex:
            logger.error("[STT] Error transcribiendo audio en memoria: %s", ex)
            return ""

    def capture_video_frame(self) -> str:
        return "frame_simulado.jpg"

    def trigger_haptic_feedback(self) -> None:
        from colorama import Fore, Style
        print(f"\n{Fore.MAGENTA}VIBRACIÓN ACTIVADA (Contexto Visual Detectado) <<<{Style.RESET_ALL}\n")

    def play_notification_sound(self) -> None:
        try:
            import winsound
            winsound.Beep(880, 90)
            return
        except Exception:
            pass
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass

    def speak_text(self, text: str) -> None:
        if not text:
            return

        from colorama import Fore, Style
        print(f"\n{Fore.YELLOW}ASISTENTE DICE: '{text}'{Style.RESET_ALL}\n")

        try:
            if self._tts_engine is None:
                import pyttsx3
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty("rate", 175)
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            return
        except Exception as ex:
            logger.debug("[TTS] pyttsx3 no disponible: %s", ex)

        try:
            safe_text = text.replace("'", "''")
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$speak.Speak('{safe_text}')"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as ex:
            logger.error("[TTS] Fallback Windows TTS fallo: %s", ex)

hardware = HardwareInterface()