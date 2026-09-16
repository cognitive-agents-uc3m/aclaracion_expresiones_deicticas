from __future__ import annotations

from dataclasses import dataclass, field

from .subject import Subject

@dataclass(frozen=True, slots=True, order=True)
class PromptRef:

    name: str
    version: str
    subject: Subject = Subject.GENERIC

    def __str__(self) -> str:
        return f"{self.name}/{self.subject.value}@{self.version}"

    @staticmethod
    def parse(raw: str) -> "PromptRef":

        name, _, rest = raw.partition("/")
        subject_raw, _, version = rest.partition("@")
        return PromptRef(
            name=name or "unknown",
            version=version or "unknown",
            subject=Subject.parse(subject_raw),
        )

@dataclass(frozen=True, slots=True)
class RenderedPrompt:

    ref: PromptRef
    system: str = ""
    user: str = ""
    variables: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.system.strip() or self.user.strip())
