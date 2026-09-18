from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .slide_html_bboxes import bboxes_in_html

_SOURCE_RANK = {
    "model-id": 0,
    "text": 0,
    "visual-order": 0,
    "text-union": 1,
    "children": 1,
    "visual-region": 2,
    "inherited": 3,
    "page": 4,
}

_BY_ROLE = {
    "title": "el título",
    "footer": "el pie de página",
    "header": "el encabezado",
    "heading": "el encabezado",
    "bullets": "la lista de viñetas",
    "body_text": "el bloque de texto",
    "equation": "la ecuación",
    "table": "la tabla",
    "chart": "el gráfico",
    "diagram": "el diagrama",
    "code": "el bloque de código",
    "figure_caption": "el pie de figura",
    "table_caption": "el título de la tabla",
    "logo_or_footer_visual": "el logotipo",
    "url": "la dirección web",
    "visual": "la imagen",
    "main_visual": "el elemento visual principal",
}

_BY_TAG = {
    "h1": "el título",
    "h2": "el título",
    "h3": "el subtítulo",
    "h4": "el subtítulo",
    "h5": "el subtítulo",
    "h6": "el subtítulo",
    "table": "la tabla",
    "caption": "el título de la tabla",
    "figure": "la figura",
    "figcaption": "el pie de figura",
    "img": "la imagen",
    "svg": "el diagrama",
    "ul": "la lista",
    "ol": "la lista numerada",
    "dl": "la lista de definiciones",
    "li": "el punto de la lista",
    "dt": "el término",
    "dd": "la definición",
    "blockquote": "la cita",
    "pre": "el bloque de código",
    "p": "el párrafo",
    "aside": "el recuadro lateral",
    "section": "la diapositiva",
    "article": "el bloque",
    "div": "el bloque",
}

_GENERIC_TAGS = frozenset({"div", "section", "article", "aside", "span"})

_POSITIONAL_ROLES = frozenset({"title", "header", "footer"})

_MAX_TEXT = 220

@dataclass(frozen=True, slots=True)
class PointedElement:

    tag: str
    kind: str

    text: str
    bbox: tuple[float, float, float, float]
    element_id: str = ""
    role: str = ""
    source: str = ""

    @property
    def is_precise(self) -> bool:

        return _SOURCE_RANK.get(self.source, 9) == 0

    @property
    def zone(self) -> str:

        x0, y0, x1, y1 = self.bbox
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        vertical = "superior" if cy < 0.34 else ("inferior" if cy > 0.66 else "central")
        horizontal = "izquierda" if cx < 0.34 else ("derecha" if cx > 0.66 else "centro")
        return f"zona {vertical} {horizontal}"

    @property
    def label(self) -> str:

        if self.text:
            return f"{self.kind} «{_shorten(self.text, 90)}»"
        return self.kind

    def as_prompt_line(self) -> str:

        partes = [self.kind]
        if self.text:
            partes.append(f"«{_shorten(self.text, _MAX_TEXT)}»")
        partes.append(f"({self.zone} de la diapositiva)")
        if not self.is_precise:
            partes.append("[posición aproximada]")
        return " ".join(partes)

def _shorten(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[:limit].rsplit(" ", 1)[0] + "…"

def _kind_of(tag: str, role: str) -> str:
    por_etiqueta = _BY_TAG.get(tag)
    if por_etiqueta and tag not in _GENERIC_TAGS:

        if tag == "p" and role in _POSITIONAL_ROLES:
            return _BY_ROLE[role]
        return por_etiqueta
    return _BY_ROLE.get(role) or por_etiqueta or "el elemento"

def element_at_point(
    html_fragment: str, x: float | None, y: float | None
) -> PointedElement | None:

    return pick_pointed_element(bboxes_in_html(html_fragment), x, y)

def pick_pointed_element(
    boxes: Sequence[Mapping[str, Any]], x: float | None, y: float | None
) -> PointedElement | None:
    if x is None or y is None:
        return None
    px, py = float(x), float(y)
    if not (0.0 <= px <= 1.0 and 0.0 <= py <= 1.0):
        return None

    best: Mapping[str, Any] | None = None
    best_key: tuple[float, int] | None = None
    for box in boxes or []:
        bbox = box.get("bbox_norm")
        if not bbox or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = (float(v) for v in bbox)
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            continue
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        key = (round(area, 6), _SOURCE_RANK.get(str(box.get("source") or ""), 9))
        if best_key is None or key < best_key:
            best, best_key = box, key

    if best is None:
        return None

    tag = str(best.get("tag") or "")
    role = str(best.get("role") or "")
    return PointedElement(
        tag=tag,
        kind=_kind_of(tag, role),
        text=" ".join(str(best.get("text") or "").split()),
        bbox=tuple(float(v) for v in best["bbox_norm"]),
        element_id=str(best.get("element_id") or ""),
        role=role,
        source=str(best.get("source") or ""),
    )

__all__ = ["PointedElement", "element_at_point", "pick_pointed_element"]
