import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))

def _rect_area(rect: Tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = rect
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)

def _rect_intersection(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    x0 = max(ax0, bx0)
    y0 = max(ay0, by0)
    x1 = min(ax1, bx1)
    y1 = min(ay1, by1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)

def _rect_iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    inter = _rect_intersection(a, b)
    if inter <= 0:
        return 0.0
    union = _rect_area(a) + _rect_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union

def _rect_distance(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = 0.0
    if ax1 < bx0:
        dx = bx0 - ax1
    elif bx1 < ax0:
        dx = ax0 - bx1
    dy = 0.0
    if ay1 < by0:
        dy = by0 - ay1
    elif by1 < ay0:
        dy = ay0 - by1
    return math.hypot(dx, dy)

def _merge_rects(rects: List[Tuple[float, float, float, float]], gap: float) -> List[Tuple[float, float, float, float]]:
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: (r[1], r[0], -(r[3] - r[1]), -(r[2] - r[0])))
    merged: List[Tuple[float, float, float, float]] = []
    for rect in rects:
        x0, y0, x1, y1 = rect
        placed = False
        for idx, current in enumerate(merged):
            if _rect_distance(current, rect) <= gap or _rect_iou(current, rect) >= 0.05:
                cx0, cy0, cx1, cy1 = current
                merged[idx] = (min(cx0, x0), min(cy0, y0), max(cx1, x1), max(cy1, y1))
                placed = True
                break
        if not placed:
            merged.append(rect)
    return merged

def _normalize_bbox(
    bbox: Tuple[float, float, float, float], page_w: float, page_h: float
) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    if page_w <= 0 or page_h <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        _clamp01(x0 / page_w),
        _clamp01(y0 / page_h),
        _clamp01(x1 / page_w),
        _clamp01(y1 / page_h),
    )

def _area_norm(bbox_norm: Tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox_norm
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)

_BULLET_RE = re.compile(r"^\s*(?:[•\-\u2022]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)])\s+")

def _assign_semantic_roles(elements: List[Dict[str, Any]]) -> None:
    if not elements:
        return

    for el in elements:
        bbox_norm = el.get("bbox_norm")
        if bbox_norm and len(bbox_norm) == 4:
            el["area_norm"] = float(_area_norm(tuple(float(v) for v in bbox_norm)))

    text_elements = [el for el in elements if str(el.get("type")) == "text"]
    max_font = 0.0
    for el in text_elements:
        try:
            max_font = max(max_font, float(el.get("font_size_max") or 0.0))
        except Exception:
            continue

    title_candidate: Optional[Dict[str, Any]] = None
    if max_font > 0 and text_elements:
        best_key: Optional[Tuple[float, float]] = None
        for el in text_elements:
            bbox = el.get("bbox_norm") or (0, 0, 0, 0)
            y0 = float(bbox[1])
            if y0 > 0.28:
                continue
            try:
                fs = float(el.get("font_size_max") or 0.0)
            except Exception:
                fs = 0.0
            if fs <= 0 or fs < 0.85 * max_font:
                continue
            key = (-fs, y0)
            if best_key is None or key < best_key:
                best_key = key
                title_candidate = el

    if title_candidate:
        title_candidate["role"] = "title"

    for el in text_elements:
        if el.get("role"):
            continue
        bbox = el.get("bbox_norm") or (0, 0, 0, 0)
        x0, y0, x1, y1 = [float(v) for v in bbox]
        height = max(0.0, y1 - y0)
        text = " ".join(str(el.get("text") or "").split()).strip()
        if y0 >= 0.90 or y1 >= 0.96:
            el["role"] = "footer"
        elif y1 <= 0.12 and height <= 0.08:
            el["role"] = "header"
        elif text and _BULLET_RE.match(text):
            el["role"] = "bullets"
        elif height >= 0.22 and (x1 - x0) >= 0.55:
            el["role"] = "body_text"
        else:
            el["role"] = "text"

    for el in elements:
        et = str(el.get("type") or "")
        if et not in {"image", "drawing"}:
            continue
        if el.get("role"):
            continue
        bbox = el.get("bbox_norm") or (0, 0, 0, 0)
        x0, y0, x1, y1 = [float(v) for v in bbox]
        area = float(el.get("area_norm") or 0.0)
        if area >= 0.28:
            el["role"] = "main_visual"
        elif y1 >= 0.92 and area <= 0.05:
            el["role"] = "logo_or_footer_visual"
        else:
            el["role"] = "visual"

def sort_elements_reading_order(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(el: Dict[str, Any]) -> Tuple[float, float, float]:
        bbox = el.get("bbox_norm") or (0, 0, 0, 0)
        x0, y0, x1, y1 = bbox
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        return (float(y0), float(x0), -float(area))

    return sorted(elements or [], key=key)

def extract_slide_elements_from_page(page: Any) -> Dict[str, Any]:
    rect = getattr(page, "rect", None)
    page_w = float(getattr(rect, "width", 0.0) or 0.0)
    page_h = float(getattr(rect, "height", 0.0) or 0.0)
    if page_w <= 0 or page_h <= 0:
        return {"page_w": page_w, "page_h": page_h, "elements": []}

    elements: List[Dict[str, Any]] = []
    min_area = (page_w * page_h) * 0.0002

    try:
        data = page.get_text("dict")
        blocks = data.get("blocks") or []
        for block in blocks:
            btype = int(block.get("type", 0))
            bbox_raw = block.get("bbox") or None
            if not bbox_raw or len(bbox_raw) != 4:
                continue
            bbox = tuple(float(v) for v in bbox_raw)
            if _rect_area(bbox) < min_area:
                continue

            if btype == 0:
                parts: List[str] = []
                sizes: List[float] = []
                for line in block.get("lines") or []:
                    for span in line.get("spans") or []:
                        text = (span.get("text") or "").strip()
                        if text:
                            parts.append(text)
                        try:
                            size = span.get("size")
                            if size is not None:
                                sizes.append(float(size))
                        except Exception:
                            pass
                text = " ".join(parts).strip()
                if not text:
                    continue
                font_size_max = max(sizes) if sizes else None
                font_size_avg = (sum(sizes) / len(sizes)) if sizes else None
                elements.append(
                    {
                        "type": "text",
                        "bbox": bbox,
                        "bbox_norm": _normalize_bbox(bbox, page_w, page_h),
                        "text": text[:700],
                        "font_size_max": font_size_max,
                        "font_size_avg": font_size_avg,
                        "span_count": len(sizes),
                    }
                )
            elif btype == 1:
                elements.append(
                    {
                        "type": "image",
                        "bbox": bbox,
                        "bbox_norm": _normalize_bbox(bbox, page_w, page_h),
                    }
                )
    except Exception:
        pass

    drawing_rects: List[Tuple[float, float, float, float]] = []
    try:
        drawings = page.get_drawings() or []
        for item in drawings:
            r = item.get("rect") if isinstance(item, dict) else None
            if not r:
                continue
            bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
            if _rect_area(bbox) < min_area:
                continue
            drawing_rects.append(bbox)
    except Exception:
        drawing_rects = []

    if drawing_rects:
        gap = max(6.0, min(page_w, page_h) * 0.01)
        merged = _merge_rects(drawing_rects, gap=gap)
        for bbox in merged[:25]:
            if _rect_area(bbox) < min_area:
                continue
            elements.append(
                {
                    "type": "drawing",
                    "bbox": bbox,
                    "bbox_norm": _normalize_bbox(bbox, page_w, page_h),
                }
            )

    deduped: List[Dict[str, Any]] = []
    for el in elements:
        bbox = el.get("bbox")
        if not bbox:
            continue
        bbox_t = tuple(bbox)
        keep = True
        for existing in deduped:
            eb = existing.get("bbox")
            if not eb:
                continue
            eb_t = tuple(eb)
            if _rect_iou(bbox_t, eb_t) >= 0.92:
                if existing.get("type") != "text" and el.get("type") == "text":
                    existing.update(el)
                keep = False
                break
        if keep:
            deduped.append(el)

    ordered = sort_elements_reading_order(deduped)
    _assign_semantic_roles(ordered)
    counters = {"text": 0, "image": 0, "drawing": 0}
    for el in ordered:
        et = str(el.get("type") or "unknown")
        counters.setdefault(et, 0)
        counters[et] += 1
        prefix = {"text": "t", "image": "img", "drawing": "v"}.get(et, "e")
        el["element_id"] = f"{prefix}{counters[et]}"

    return {"page_w": page_w, "page_h": page_h, "elements": ordered}


def format_elements_inventory(elements: List[Dict[str, Any]]) -> str:
    ordered = sort_elements_reading_order(elements or [])
    if not ordered:
        return "[Inventario por bounding boxes]\nninguno"

    lines: List[str] = ["[Inventario por bounding boxes]"]
    for idx, el in enumerate(ordered, start=1):
        bbox = el.get("bbox_norm") or (0, 0, 0, 0)
        x0, y0, x1, y1 = [round(float(v), 4) for v in bbox]
        etype = str(el.get("type") or "desconocido")
        eid = str(el.get("element_id") or f"e{idx}")
        role = str(el.get("role") or "").strip()
        extra = f" | rol={role}" if role else ""
        lines.append(
            f"[Bounding box {idx} | id={eid} | tipo={etype}{extra} | bbox_norm={x0},{y0},{x1},{y1}]"
        )
        if etype == "text":
            text = " ".join(str(el.get("text") or "").split()).strip()
            if not text:
                text = "texto no legible"
            fs = el.get("font_size_max")
            fs_hint = ""
            try:
                if fs is not None:
                    fs_hint = f" (fs_max={round(float(fs), 1)})"
            except Exception:
                fs_hint = ""
            lines.append(f"Texto{fs_hint}: {text[:420]}")
        else:
            hint = "elemento visual"
            lines.append(f"Contenido: {hint}")
        lines.append("")
    return "\n".join(lines).rstrip()


def pick_element_for_point(
    elements: List[Dict[str, Any]], x_norm: Optional[float], y_norm: Optional[float]
) -> Optional[Dict[str, Any]]:
    if x_norm is None or y_norm is None:
        return None
    x = float(x_norm)
    y = float(y_norm)
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None

    ordered = elements or []
    inside: List[Tuple[float, Dict[str, Any]]] = []
    for el in ordered:
        bbox = el.get("bbox_norm")
        if not bbox or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = [float(v) for v in bbox]
        if x0 <= x <= x1 and y0 <= y <= y1:
            area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
            inside.append((area, el))
    if inside:
        inside.sort(key=lambda item: item[0])
        return inside[0][1]

    best = None
    best_d = float("inf")
    for el in ordered:
        bbox = el.get("bbox_norm")
        if not bbox or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = [float(v) for v in bbox]
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        d = math.hypot(x - cx, y - cy)
        if d < best_d:
            best_d = d
            best = el
    return best


def elements_to_json(elements: List[Dict[str, Any]]) -> str:
    return json.dumps(elements or [], ensure_ascii=False)


def elements_from_json(payload: Optional[str]) -> List[Dict[str, Any]]:
    raw = (payload or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [el for el in data if isinstance(el, dict)]
    except Exception:
        return []
    return []