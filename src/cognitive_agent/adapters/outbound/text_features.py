from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from scipy.sparse import csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin

def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))

_PATTERNS = (
    r"\b(?:en concreto|concretamente|es decir|para ser precis[oa])\b",
    r"\bse (?:refiere|esta haciendo referencia) a\b",
    r"\bse trata de\b",
    r"\b(?:el )?(?:nombre del )?referente\b",
    r"\breferencia (?:queda )?identificad[ao]\b",
    r"\b(?:elemento|parte|objeto) (?:concreto |mencionado |indicado |senalado )?es\b",
    r"\b(?:identificad[ao]|denominad[ao]|llamad[ao]) como\b",
    r"\b(?:se llama|me refiero a|hablo de)\b",
    r"\bcorresponde exactamente a\b",
    r"\bque es (?:el|la|los|las|un|una|\d)\b",
    r"\bque son (?:el|la|los|las|\d)\b",
    r"\b(?:es|son) (?:\d+(?:[,.]\d+)?|[A-Z]{2,}[\w-]*)\b",
)

class ExplicitReferenceFeatures(TransformerMixin, BaseEstimator):

    def fit(self, texts: Iterable[str], y=None):
        return self

    def transform(self, texts: Iterable[str]):
        rows: list[list[float]] = []
        for raw_text in texts:
            text = _normalize(str(raw_text))
            marker_values = [float(bool(re.search(pattern, text))) for pattern in _PATTERNS]
            rows.append(
                [
                    *marker_values,
                    float(bool(re.search(r"\b\d+(?:[,.]\d+)?\b", text))),
                ]
            )
        return csr_matrix(rows, dtype=float)

__all__ = ["ExplicitReferenceFeatures"]
