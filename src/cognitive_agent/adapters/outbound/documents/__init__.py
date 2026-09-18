from .gemini_slide_detection import GeminiSlideElementDetector
from .pointer_resolver import DescriptionAwarePointerResolver
from .pymupdf_source import DECK_ID_VERSION, DeckInfo, PyMuPdfDocumentSource

__all__ = [
    "DECK_ID_VERSION",
    "DeckInfo",
    "DescriptionAwarePointerResolver",
    "GeminiSlideElementDetector",
    "PyMuPdfDocumentSource",
]
