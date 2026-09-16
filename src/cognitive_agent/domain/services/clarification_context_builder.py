from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING

from ..entities.classroom_session import ClassroomSession
from ..errors import SlideDescriptionUnavailable
from ..value_objects.deictic import DeicticExpression
from ..value_objects.identifiers import SessionId, SlideIdentifier
from ..value_objects.slide_description import SlideDescription
from ..value_objects.subject import Subject
from ..value_objects.transcript import TranscriptFragment

if TYPE_CHECKING:
    from ..entities.clarification import Clarification

@dataclass(frozen=True, slots=True)
class ClarificationContext:

    session_id: SessionId
    subject: Subject
    slide: SlideIdentifier
    slide_count: int
    utterance: str

    recent_context: str

    slide_description: str

    expression: DeicticExpression | None = None
    visual_focus: str = ""

    pointed_element: str = ""

    max_words: int = 45

    @property
    def slide_number(self) -> int:
        return self.slide.number

    @property
    def expression_text(self) -> str:
        return self.expression.surface if self.expression else "sin expresion deictica explicita"

    def as_variables(self) -> dict[str, str]:

        return {
            "DEICTIC_EXPRESSION": self.expression_text,
            "VISUAL_FOCUS": self.visual_focus or "sin foco explicito",
            "POINTED_ELEMENT": self.pointed_element or "sin puntero / sin elemento resuelto",
            "SPEAKER_UTTERANCE": self.utterance or "sin contexto",
            "RECENT_CONTEXT": self.recent_context or "sin contexto previo",
            "SLIDE_DESCRIPTION": self.slide_description or "sin descripcion disponible",
            "SLIDE_NUMBER": str(self.slide_number),
            "SLIDE_COUNT": str(self.slide_count),
            "MAX_WORDS": str(self.max_words),
        }

class ClarificationContextBuilder:

    def __init__(self, *, max_words: int = 45, max_description_chars: int = 4000) -> None:
        self._max_words = max_words
        self._max_description_chars = max_description_chars

    def build(
        self,
        *,
        session: ClassroomSession,
        fragment: TranscriptFragment,
        description: SlideDescription | None,
        expression: DeicticExpression | None = None,
        visual_focus: str = "",
        pointed_element: str = "",
        require_description: bool = True,
    ) -> ClarificationContext:

        slide = fragment.slide or session.current_slide
        if slide is None:
            raise SlideDescriptionUnavailable(
                "No hay diapositiva activa a la que referir la aclaracion."
            )

        if description is None or not description.is_ready:
            if require_description:
                raise SlideDescriptionUnavailable(
                    f"La descripcion accesible de la diapositiva {slide.number} no esta lista."
                )
            description_text = ""
        else:
            description_text = description.excerpt(self._max_description_chars)

        return ClarificationContext(
            session_id=session.session_id,
            subject=session.subject,
            slide=slide,
            slide_count=session.slide_count,
            utterance=fragment.normalized,
            recent_context=session.context.preceding_text(),
            slide_description=description_text,
            expression=expression,
            visual_focus=visual_focus,
            pointed_element=pointed_element,
            max_words=self._max_words,
        )

    def rebuild(
        self,
        *,
        clarification: "Clarification",
        description: SlideDescription | None,
        subject: Subject,
        slide_count: int,
        require_description: bool = True,
    ) -> ClarificationContext:

        if description is None or not description.is_ready:
            if require_description:
                raise SlideDescriptionUnavailable(
                    f"La descripcion accesible de la diapositiva "
                    f"{clarification.slide.number} no esta lista."
                )
            description_text = ""
        else:
            description_text = description.excerpt(self._max_description_chars)

        return ClarificationContext(
            session_id=clarification.session_id,
            subject=subject,
            slide=clarification.slide,
            slide_count=slide_count,
            utterance=clarification.trigger_fragment,
            recent_context=clarification.recent_context,
            slide_description=description_text,
            expression=clarification.trigger_expression,
            pointed_element=clarification.pointed_element,
            max_words=self._max_words,
        )
