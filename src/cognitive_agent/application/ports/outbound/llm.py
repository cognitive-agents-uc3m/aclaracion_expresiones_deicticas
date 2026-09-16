from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from ....domain.services.clarification_context_builder import ClarificationContext
from ....domain.value_objects.deictic import DeicticDetection
from ....domain.value_objects.identifiers import SlideIdentifier
from ....domain.value_objects.slide_description import SlideDescription
from ....domain.value_objects.subject import Subject
from ...dto import GeneratedClarification

@runtime_checkable
class DeicticDetectorPort(Protocol):

    name: str

    def detect(self, text: str, *, subject: Subject = Subject.GENERIC) -> DeicticDetection: ...

@runtime_checkable
class ClarificationGeneratorPort(Protocol):

    name: str

    def generate(self, context: ClarificationContext) -> GeneratedClarification:

        ...

@runtime_checkable
class SlideDescriptionGeneratorPort(Protocol):

    name: str

    def describe(
        self,
        *,
        slide: SlideIdentifier,
        slide_count: int,
        subject: Subject,
        image: bytes | None = None,
        pdf_page: bytes | None = None,
        layout: Mapping[str, Any] | None = None,
    ) -> SlideDescription:

        ...

@runtime_checkable
class PointedElementResolverPort(Protocol):

    def describe_point(
        self,
        *,
        document_path: str,
        slide_index: int,
        x: float,
        y: float,
        deck_id: str = "",
    ) -> str:

        ...

@runtime_checkable
class NotesProcessorPort(Protocol):

    name: str

    def process(self, raw_text: str, *, subject: Subject = Subject.GENERIC) -> str: ...
