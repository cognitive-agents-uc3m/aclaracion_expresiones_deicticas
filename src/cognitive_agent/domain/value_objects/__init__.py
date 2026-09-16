from .content_source import ContentSource
from .deictic import DeicticDetection, DeicticExpression, DeicticKind
from .identifiers import (
    ClarificationId,
    DeckId,
    FragmentId,
    NoteEntryId,
    SessionId,
    SlideIdentifier,
)
from .prompt import PromptRef, RenderedPrompt
from .slide_description import DescriptionFormat, DescriptionStatus, SlideDescription
from .subject import Subject
from .tags import (
    CLARIFICATION_TAG_PATTERN,
    DEFAULT_CLARIFICATION_TAG_TEMPLATE,
    DEFAULT_SLIDE_TAG_TEMPLATE,
    SLIDE_TAG_PATTERN,
    ClarificationTag,
    SlideTag,
)
from .transcript import TranscriptContext, TranscriptFragment, fold_accents, normalize_text

__all__ = [
    "CLARIFICATION_TAG_PATTERN",
    "DEFAULT_CLARIFICATION_TAG_TEMPLATE",
    "DEFAULT_SLIDE_TAG_TEMPLATE",
    "SLIDE_TAG_PATTERN",
    "ClarificationId",
    "ClarificationTag",
    "ContentSource",
    "DeckId",
    "DeicticDetection",
    "DeicticExpression",
    "DeicticKind",
    "DescriptionFormat",
    "DescriptionStatus",
    "FragmentId",
    "NoteEntryId",
    "PromptRef",
    "RenderedPrompt",
    "SessionId",
    "SlideDescription",
    "SlideIdentifier",
    "SlideTag",
    "Subject",
    "TranscriptContext",
    "TranscriptFragment",
    "fold_accents",
    "normalize_text",
]
