from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from ....domain.services.slide_layout import (
    format_elements_inventory,
    pick_element_for_point,
)

logger = logging.getLogger(__name__)

DECK_ID_VERSION = "v3-gemini-elements"

@dataclass(frozen=True, slots=True)
class DeckInfo:
    deck_id: str
    slide_count: int
    path: str
    title: str = ""

    @property
    def is_empty(self) -> bool:
        return self.slide_count == 0

class PyMuPdfDocumentSource:
    def __init__(
        self,
        *,
        render_scale: float = 1.6,
        cache_dir: str | None = None,
        element_detector=None,
        processing_profile: str = "",
    ) -> None:
        self._scale = render_scale
        self._element_detector = element_detector
        self._processing_profile = processing_profile.strip()
        self._cache_dir = Path(cache_dir or os.path.join(tempfile.gettempdir(), "cognitive_agent_slides"))
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._render_cache: dict[tuple[str, int], str] = {}
        self._layout_cache: dict[tuple[str, int], dict] = {}

    @staticmethod
    def fingerprint(path: str | Path) -> str:

        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def deck_id_for(cls, path: str | Path, *, profile: str = "") -> str:

        suffix = f":{profile}" if profile else ""
        return f"{cls.fingerprint(path)}:{DECK_ID_VERSION}{suffix}"

    def open_deck(self, path: str | Path, *, profile: str = "") -> DeckInfo:
        import fitz

        resolved = str(Path(path).resolve())
        with fitz.open(resolved) as document:
            count = document.page_count
            metadata = document.metadata or {}
            title = str(metadata.get("title") or "").strip()
        effective_profile = ":".join(
            part for part in (profile.strip(), self._processing_profile) if part
        )
        return DeckInfo(
            deck_id=self.deck_id_for(resolved, profile=effective_profile),
            slide_count=count,
            path=resolved,
            title=title or Path(resolved).stem,
        )

    def render_slide(self, path: str | Path, index: int) -> str:

        import fitz

        resolved = str(Path(path).resolve())
        key = (resolved, int(index))
        cached = self._render_cache.get(key)
        if cached and os.path.exists(cached):
            return cached

        digest = hashlib.md5(f"{resolved}:{index}:{self._scale}".encode("utf-8")).hexdigest()
        out_path = str(self._cache_dir / f"{digest}.png")
        with fitz.open(resolved) as document:
            page = document.load_page(int(index))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(self._scale, self._scale), alpha=False)
            pixmap.save(out_path)
        self._render_cache[key] = out_path
        return out_path

    def slide_image_bytes(self, path: str | Path, index: int) -> bytes:
        with open(self.render_slide(path, index), "rb") as handle:
            return handle.read()

    def slide_pdf_bytes(self, path: str | Path, index: int) -> bytes:

        import fitz

        with fitz.open(str(Path(path).resolve())) as document:
            single = fitz.open()
            try:
                single.insert_pdf(document, from_page=int(index), to_page=int(index))
                return single.tobytes()
            finally:
                single.close()

    def slide_layout(self, path: str | Path, index: int) -> dict:
        if self._element_detector is None:
            raise RuntimeError("No hay detector visual configurado para segmentar diapositivas.")

        import fitz

        resolved = str(Path(path).resolve())
        key = (resolved, int(index))
        cached = self._layout_cache.get(key)
        if cached is not None:
            return cached

        with fitz.open(resolved) as document:
            page = document.load_page(int(index))
            page_w = float(page.rect.width)
            page_h = float(page.rect.height)
        elements = self._element_detector.detect(self.slide_image_bytes(resolved, index))
        layout = {"page_w": page_w, "page_h": page_h, "elements": elements}
        self._layout_cache[key] = layout
        return layout

    def slide_elements(self, path: str | Path, index: int) -> list[dict]:
        return list(self.slide_layout(path, index).get("elements") or [])

    def slide_inventory(self, path: str | Path, index: int) -> str:
        return format_elements_inventory(self.slide_elements(path, index))

    def element_at(self, path: str | Path, index: int, x: float, y: float) -> dict | None:
        return pick_element_for_point(self.slide_elements(path, index), x, y)

    def describe_point(
        self,
        *,
        document_path: str,
        slide_index: int,
        x: float,
        y: float,
        deck_id: str = "",
    ) -> str:

        resolved = str(Path(document_path).resolve())
        layout = self._layout_cache.get((resolved, int(slide_index)))
        if layout is None:
            # Resolver el puntero nunca debe provocar una llamada nueva a
            # Gemini. El flujo principal usa las cajas persistidas en HTML;
            # este respaldo solo consulta detecciones ya precalculadas.
            return ""
        try:
            elemento = pick_element_for_point(list(layout.get("elements") or []), x, y)
        except Exception as exc:
            logger.debug("No se pudo resolver el elemento senalado: %s", exc)
            return ""
        if not elemento:
            return ""

        partes = [f"id={elemento.get('element_id', '-')}", f"tipo={elemento.get('type', '-')}"]
        rol = str(elemento.get("role") or "").strip()
        if rol:
            partes.append(f"rol={rol}")
        bbox = elemento.get("bbox_norm")
        if bbox:
            partes.append("bbox_norm=" + ",".join(f"{float(v):.3f}" for v in bbox))
        clase = str(elemento.get("class") or "").strip()
        if clase:
            partes.append(f"clase={clase}")
        nivel2 = str(elemento.get("nivel2") or "").strip()
        if nivel2:
            partes.append(f"nivel2={nivel2}")
        texto = " ".join(
            str(elemento.get("text") or elemento.get("description") or "").split()
        ).strip()
        if texto:
            partes.append(f"texto='{texto[:280]}'")
        return " ".join(partes)

    def cleanup(self) -> None:
        for cached in list(self._render_cache.values()):
            try:
                if os.path.exists(cached):
                    os.unlink(cached)
            except OSError:
                pass
        self._render_cache.clear()
        self._layout_cache.clear()
