from __future__ import annotations

import logging
from ....domain.services.pointed_element import PointedElement, element_at_point
from ....domain.value_objects.identifiers import DeckId, SlideIdentifier
from ....domain.value_objects.slide_description import DescriptionFormat

logger = logging.getLogger(__name__)

class DescriptionAwarePointerResolver:

    name = "description_aware"

    def __init__(self, *, descriptions, fallback=None) -> None:
        self._descriptions = descriptions
        self._fallback = fallback

    def element_at(
        self, *, deck_id: str, slide_index: int, x: float, y: float
    ) -> PointedElement | None:

        if not deck_id:
            return None
        try:
            description = self._descriptions.get(
                SlideIdentifier(DeckId(deck_id), int(slide_index))
            )
        except Exception:
            logger.debug("No se pudo leer la descripcion para situar el puntero.", exc_info=True)
            return None
        if description is None or not description.is_ready:
            return None
        if description.fmt is not DescriptionFormat.HTML:
            return None
        return element_at_point(description.content, x, y)

    def describe_point(
        self,
        *,
        document_path: str,
        slide_index: int,
        x: float,
        y: float,
        deck_id: str = "",
    ) -> str:
        elemento = self.element_at(deck_id=deck_id, slide_index=slide_index, x=x, y=y)
        if elemento is not None:
            return elemento.as_prompt_line()
        if self._fallback is None or not document_path:
            return ""
        try:
            return self._fallback.describe_point(
                document_path=document_path, slide_index=slide_index, x=x, y=y
            )
        except Exception:
            logger.debug("El respaldo geometrico tampoco pudo situar el puntero.", exc_info=True)
            return ""

__all__ = ["DescriptionAwarePointerResolver"]
