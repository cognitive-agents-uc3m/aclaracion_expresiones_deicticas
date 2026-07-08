
import hashlib
import os
import tempfile
from typing import Dict, Optional, Tuple
import fitz

class SlideRenderCache:

    def __init__(self, cache_dir_name: str, scale: float = 2.0):
        self._scale = float(scale)
        self._cache: Dict[Tuple[str, int], str] = {}
        self._cache_dir = os.path.join(tempfile.gettempdir(), cache_dir_name)
        os.makedirs(self._cache_dir, exist_ok=True)

    def render(self, pdf_path: Optional[str], slide_index: int, slide_count: int) -> Optional[str]:
        if not pdf_path or slide_count <= 0:
            return None
        idx = max(0, min(int(slide_index), slide_count - 1))
        cache_key = (pdf_path, idx)
        cached = self._cache.get(cache_key)
        if cached and os.path.exists(cached):
            return cached

        with fitz.open(pdf_path) as doc:
            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=fitz.Matrix(self._scale, self._scale), alpha=False)
            digest = hashlib.md5(f"{pdf_path}:{idx}".encode("utf-8")).hexdigest()
            out_path = os.path.join(self._cache_dir, f"{digest}.png")
            pix.save(out_path)
        self._cache[cache_key] = out_path
        return out_path