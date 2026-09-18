from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.value_objects.subject import Subject
from ..domain.value_objects.tags import (
    DEFAULT_CLARIFICATION_TAG_TEMPLATE,
    DEFAULT_SLIDE_TAG_TEMPLATE,
)

@dataclass(frozen=True, slots=True)
class SessionSettings:
    default_subject: Subject = Subject.GENERIC
    transcript_window: int = 6
    context_max_previous_fragments: int = 4
    context_max_age_seconds: float = 30.0
    context_max_chars: int = 1000
    context_keep_after_clarification: int = 2

@dataclass(frozen=True, slots=True)
class NotesSettings:
    slide_tag_idle_seconds: float = 2.0

    slide_tag_template: str = DEFAULT_SLIDE_TAG_TEMPLATE
    clarification_tag_template: str = DEFAULT_CLARIFICATION_TAG_TEMPLATE
    auto_insert_clarifications: bool = False
    tag_empty_notes: bool = False
    announce_tag_insertion: bool = True

@dataclass(frozen=True, slots=True)
class ClarificationSettings:
    auto_play: bool = False
    announce_availability: bool = True
    notification_sound: bool = True
    timeout_seconds: float = 20.0
    min_seconds_between: float = 3.0
    max_words: int = 45
    on_stale_slide: str = "keep"
    require_description: bool = False

    @property
    def discard_when_stale(self) -> bool:
        return self.on_stale_slide.strip().lower() == "discard"

@dataclass(frozen=True, slots=True)
class DeixisSettings:
    detector: str = "rules"
    min_confidence: float = 0.5
    classifier_model_path: str = "models/deixis_classifier.joblib"
    classifier_threshold: float = -1.0

@dataclass(frozen=True, slots=True)
class AccessibilitySettings:

    shortcuts: dict[str, str] = field(
        default_factory=lambda: {
            "listen_clarification": "F7",
            "announce_slide": "F8",
            "insert_clarification": "F9",
            "jump_to_slide_notes": "F2",
        }
    )
    live_region_politeness: str = "polite"
    clarification_politeness: str = "assertive"
    sounds_enabled: bool = True
    announce_slide_changes: bool = True

    def shortcut(self, action: str) -> str:
        return self.shortcuts.get(action, "")

@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    session: SessionSettings = field(default_factory=SessionSettings)
    notes: NotesSettings = field(default_factory=NotesSettings)
    clarification: ClarificationSettings = field(default_factory=ClarificationSettings)
    deixis: DeixisSettings = field(default_factory=DeixisSettings)
    accessibility: AccessibilitySettings = field(default_factory=AccessibilitySettings)
