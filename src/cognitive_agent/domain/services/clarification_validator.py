from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")

_PREFACES = re.compile(
    r"^(?:"
    r"(?:en|dentro\s+de)\s+(?:la\s+)?(?:diapositiva|imagen|figura|pantalla|transparencia)[^,.:]*[,.:]\s*"
    r"|(?:aqui|ahi)\s+(?:se\s+)?(?:puede\s+)?(?:ver|verse|observar)[^,.:]*[,.:]\s*"
    r"|(?:podemos|podeis|se\s+puede)\s+ver(?:\s+que)?[,:]?\s+"
    r"|(?:observamos|vemos|se\s+observa|se\s+aprecia)(?:\s+que)?[,:]?\s+"
    r"|la\s+imagen\s+muestra\s+"

    r"|[\"'«]?(?:esto|eso|aqui|ahi)[\"'»]?\s+(?:se\s+refiere\s+a|hace\s+referencia\s+a|apunta\s+a)\s+"
    r"|la\s+expresion\s+[^,.:]*[,.:]\s*"
    r"|el\s+orador\s+(?:senala|indica|se\s+refiere)[^,.:]*[,.:]\s*"
    r")",
    re.IGNORECASE,
)

_THINKING = re.compile(r"^\s*(?:<think>.*?</think>|\[?(?:pensando|razonamiento)\]?:.*?)\s*", re.IGNORECASE | re.DOTALL)

@dataclass(frozen=True, slots=True)
class ValidationResult:
    text: str
    is_valid: bool
    reason: str = ""
    truncated: bool = False
    preface_removed: bool = False

    @property
    def word_count(self) -> int:
        return len(self.text.split())

class ClarificationValidator:
    def __init__(self, *, max_words: int = 45, min_chars: int = 3) -> None:
        self._max_words = max_words
        self._min_chars = min_chars

    def validate(self, raw: str) -> ValidationResult:
        text = _THINKING.sub("", raw or "").strip()
        text = _WS.sub(" ", text).strip()

        if len(text) >= 2 and text[0] in "\"'«" and text[-1] in "\"'»":
            text = text[1:-1].strip()

        if len(text) < self._min_chars:
            return ValidationResult("", False, "la generacion devolvio texto vacio")

        without_preface = _PREFACES.sub("", text, count=1).strip()
        preface_removed = without_preface != text
        if without_preface:
            text = without_preface[0].upper() + without_preface[1:]

        if not text:
            text = _WS.sub(" ", raw).strip()
            preface_removed = False

        truncated = False
        words = text.split()
        if len(words) > self._max_words:
            truncated = True
            clipped = " ".join(words[: self._max_words])

            cut = max(clipped.rfind(". "), clipped.rfind("; "))
            text = (clipped[: cut + 1] if cut > len(clipped) // 2 else clipped).rstrip(" ,;:")
            if not text.endswith((".", "!", "?")):
                text += "."

        if not text.endswith((".", "!", "?", ":")):
            text += "."

        return ValidationResult(
            text=text,
            is_valid=True,
            truncated=truncated,
            preface_removed=preface_removed,
        )
