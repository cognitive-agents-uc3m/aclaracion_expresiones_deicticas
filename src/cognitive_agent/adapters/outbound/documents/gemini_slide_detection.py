from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

LEVEL1_CLASSES = (
    "Title",
    "Heading",
    "Description",
    "Enumeration",
    "Equation",
    "Table",
    "Chart",
    "Diagram",
    "Code",
    "Figure-Caption",
    "Table-Caption",
    "Logo",
    "Footer-Element",
    "SlideNr",
    "URL",
    "Natural-Image",
)

LEVEL2_CLASSES = (
    "Line graph",
    "Natural image",
    "Table",
    "3D object",
    "Bar plot",
    "Scatter plot",
    "Medical image",
    "Sketch",
    "Geographic map",
    "Flow chart",
    "Heat map",
    "Mask",
    "Block diagram",
    "Venn diagram",
    "Confusion matrix",
    "Histogram",
    "Box plot",
    "Vector plot",
    "Pie chart",
    "Surface plot",
    "Algorithm",
    "Contour plot",
    "Tree diagram",
    "Bubble chart",
    "Polar plot",
    "Area chart",
    "Pareto chart",
    "Radar chart",
)

_TEXT_CLASSES = frozenset(
    {
        "Title",
        "Heading",
        "Description",
        "Enumeration",
        "Equation",
        "Code",
        "Figure-Caption",
        "Table-Caption",
        "Footer-Element",
        "SlideNr",
        "URL",
    }
)

_IMAGE_CLASSES = frozenset({"Natural-Image", "Logo"})
_CASCADE_CLASSES = frozenset({"Diagram", "Chart"})

_ROLES = {
    "Title": "title",
    "Heading": "heading",
    "Description": "body_text",
    "Enumeration": "bullets",
    "Equation": "equation",
    "Table": "table",
    "Chart": "chart",
    "Diagram": "diagram",
    "Code": "code",
    "Figure-Caption": "figure_caption",
    "Table-Caption": "table_caption",
    "Logo": "logo_or_footer_visual",
    "Footer-Element": "footer",
    "SlideNr": "footer",
    "URL": "url",
    "Natural-Image": "visual",
}

LEVEL1_PROMPT = f"""Analiza esta diapositiva de una presentacion academica.
Escanea visualmente el documento de arriba abajo y de izquierda a derecha.

Detecta TODAS las regiones visuales que pertenezcan a alguna de estas categorias:
{', '.join(LEVEL1_CLASSES)}

Para cada region devuelve sus coordenadas [ymin, xmin, ymax, xmax] normalizadas
en una escala de 0 a 1000. [0, 0] es la esquina superior izquierda y
[1000, 1000] la esquina inferior derecha.

En "descripcion", para elementos textuales copia literalmente el texto visible.
Para tablas, imagenes, graficos y diagramas escribe una descripcion breve y factual.

Devuelve UNICAMENTE un array JSON valido, sin Markdown, con esta estructura:
[
  {{
    "descripcion": "texto visible o descripcion breve",
    "label": "categoria_exacta",
    "box_2d": [150, 50, 450, 900]
  }}
]"""

LEVEL2_PROMPT = f"""Esta imagen es el recorte de un unico diagrama o grafico
extraido de una diapositiva academica. Clasificalo en EXACTAMENTE una de estas
categorias del dataset DocFigure:
{', '.join(LEVEL2_CLASSES)}

Devuelve UNICAMENTE la categoria exacta, sin explicacion, comillas ni puntuacion."""


@dataclass(slots=True)
class GeminiSlideElementDetector:
    """Detecta regiones semanticas de una diapositiva mediante un modelo visual."""

    vision: Any
    timeout_seconds: float = 180.0
    crop_padding: float = 0.05
    crop_min_side: int = 768

    def detect(self, image: bytes, *, mime_type: str = "image/png") -> list[dict[str, Any]]:
        response = self.vision.describe(
            prompt=LEVEL1_PROMPT,
            image=image,
            mime_type=mime_type,
            timeout_seconds=self.timeout_seconds,
        )
        raw_detections = _extract_json_array(response.text)
        detections: list[dict[str, Any]] = []

        for raw in raw_detections:
            detection = _normalise_detection(raw)
            if detection is None:
                continue
            if detection["class"] in _CASCADE_CLASSES:
                try:
                    crop = _crop_and_upscale(
                        image,
                        detection["bbox_norm"],
                        padding=self.crop_padding,
                        min_side=self.crop_min_side,
                    )
                    detection["nivel2"] = self._classify_level2(crop)
                except Exception as exc:
                    logger.warning(
                        "No se pudo clasificar el segundo nivel de %s: %s",
                        detection["class"],
                        exc,
                    )
                    detection["nivel2"] = None
            detections.append(detection)

        _assign_ids(detections)
        return detections

    def _classify_level2(self, crop: bytes) -> str | None:
        response = self.vision.describe(
            prompt=LEVEL2_PROMPT,
            image=crop,
            mime_type="image/png",
            timeout_seconds=self.timeout_seconds,
        )
        candidate = (response.text or "").strip().strip("`\"' .")
        for category in LEVEL2_CLASSES:
            if candidate.casefold() == category.casefold():
                return category
        logger.warning("Gemini devolvio una categoria de nivel 2 desconocida: %r", candidate)
        return None


def _extract_json_array(text: str) -> list[Mapping[str, Any]]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Gemini no devolvio un array JSON de detecciones.")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, list):
        raise ValueError("La respuesta de deteccion no es una lista.")
    return [item for item in payload if isinstance(item, Mapping)]


def _normalise_detection(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    label_raw = str(raw.get("label") or raw.get("class") or "").strip()
    label = next((item for item in LEVEL1_CLASSES if item.casefold() == label_raw.casefold()), None)
    box = raw.get("box_2d") or raw.get("box")
    if label is None or not isinstance(box, Sequence) or isinstance(box, (str, bytes)):
        return None
    if len(box) != 4:
        return None
    try:
        ymin, xmin, ymax, xmax = (float(value) for value in box)
    except (TypeError, ValueError):
        return None

    scale = 1000.0 if max(abs(ymin), abs(xmin), abs(ymax), abs(xmax)) > 1.5 else 1.0
    x0, x1 = sorted((_clamp01(xmin / scale), _clamp01(xmax / scale)))
    y0, y1 = sorted((_clamp01(ymin / scale), _clamp01(ymax / scale)))
    if x1 <= x0 or y1 <= y0:
        return None

    description = " ".join(str(raw.get("descripcion") or raw.get("description") or "").split())
    element_type = "text" if label in _TEXT_CLASSES else ("image" if label in _IMAGE_CLASSES else "drawing")
    result: dict[str, Any] = {
        "type": element_type,
        "role": _ROLES[label],
        "class": label,
        "bbox_norm": (x0, y0, x1, y1),
        "area_norm": (x1 - x0) * (y1 - y0),
        "description": description[:700],
    }
    if element_type == "text":
        result["text"] = description[:700]
    return result


def _assign_ids(detections: list[dict[str, Any]]) -> None:
    detections.sort(
        key=lambda item: (
            float(item["bbox_norm"][1]),
            float(item["bbox_norm"][0]),
            -float(item["area_norm"]),
        )
    )
    counters = {"text": 0, "image": 0, "drawing": 0}
    prefixes = {"text": "t", "image": "img", "drawing": "v"}
    for detection in detections:
        kind = str(detection["type"])
        counters[kind] += 1
        detection["element_id"] = f"{prefixes[kind]}{counters[kind]}"


def _crop_and_upscale(
    image_bytes: bytes,
    bbox: Sequence[float],
    *,
    padding: float,
    min_side: int,
) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    x0, y0, x1, y1 = (float(value) for value in bbox)
    pad_x, pad_y = (x1 - x0) * padding, (y1 - y0) * padding
    x0, x1 = max(0.0, x0 - pad_x), min(1.0, x1 + pad_x)
    y0, y1 = max(0.0, y0 - pad_y), min(1.0, y1 + pad_y)
    crop = image.crop((int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)))
    longest = max(crop.size)
    if 0 < longest < min_side:
        factor = min_side / longest
        crop = crop.resize(
            (round(crop.width * factor), round(crop.height * factor)), Image.Resampling.LANCZOS
        )
    output = io.BytesIO()
    crop.save(output, format="PNG")
    return output.getvalue()

def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))

__all__ = [
    "GeminiSlideElementDetector",
    "LEVEL1_CLASSES",
    "LEVEL2_CLASSES",
    "LEVEL1_PROMPT",
    "LEVEL2_PROMPT",
]
