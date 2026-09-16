from __future__ import annotations

from enum import Enum

class ContentSource(str, Enum):
    STUDENT = "student"
    SYSTEM = "system"
    TEACHER = "teacher"
    LLM = "llm"

    @property
    def is_editable_by_student(self) -> bool:
        return self is ContentSource.STUDENT
