from __future__ import annotations

import html as html_lib
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping, Sequence

BBOX_ATTR = "data-bbox"
BBOX_ABS_ATTR = "data-bbox-abs"
BBOX_SOURCE_ATTR = "data-bbox-source"
BBOX_ROLE_ATTR = "data-bbox-role"
ELEMENT_ID_ATTR = "data-element-id"
PAGE_WIDTH_ATTR = "data-slide-width"
PAGE_HEIGHT_ATTR = "data-slide-height"
BBOX_SPACE_ATTR = "data-bbox-space"

ELEMENT_IDS_ATTR = "data-element-ids"

_MANAGED = frozenset(
    {
        BBOX_ATTR,
        BBOX_ABS_ATTR,
        BBOX_SOURCE_ATTR,
        BBOX_ROLE_ATTR,
        PAGE_WIDTH_ATTR,
        PAGE_HEIGHT_ATTR,
        BBOX_SPACE_ATTR,
        ELEMENT_ID_ATTR,
        ELEMENT_IDS_ATTR,
    }
)

_VOID = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)

_BLOCK = frozenset(
    {
        "section", "article", "aside", "div", "header", "footer", "nav",
        "h1", "h2", "h3", "h4", "h5", "h6", "p",
        "ul", "ol", "li", "dl", "dt", "dd",
        "table", "caption", "figure", "figcaption", "blockquote", "pre",
    }
)

_VISUAL = frozenset({"figure", "img", "svg", "picture"})

_CONTAINMENT = 0.7

_COVERAGE = 0.7

_WORD = re.compile(r"[0-9a-z]+")

_FULL_PAGE = (0.0, 0.0, 1.0, 1.0)

Bbox = tuple[float, float, float, float]

def _tokens(text: str) -> frozenset[str]:

    lowered = unicodedata.normalize("NFKD", (text or "").lower())
    plain = "".join(c for c in lowered if not unicodedata.combining(c))
    return frozenset(_WORD.findall(plain))

def _as_bbox(value: Any) -> Bbox | None:
    if not value:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    return (x0, y0, x1, y1)

def _union(boxes: Iterable[Bbox]) -> Bbox | None:
    result: Bbox | None = None
    for box in boxes:
        if result is None:
            result = box
            continue
        result = (
            min(result[0], box[0]),
            min(result[1], box[1]),
            max(result[2], box[2]),
            max(result[3], box[3]),
        )
    return result

def _fmt(value: float, decimals: int) -> str:
    return f"{round(float(value), decimals):g}"

def _fmt_bbox(bbox: Bbox, decimals: int) -> str:
    return ",".join(_fmt(v, decimals) for v in bbox)

@dataclass(slots=True)
class _Box:
    element_id: str
    type: str
    role: str
    bbox: Bbox
    tokens: frozenset[str]
    area: float
    used: bool = False

def _inventory(elements: Sequence[Mapping[str, Any]] | None) -> list[_Box]:

    boxes: list[_Box] = []
    for raw in elements or []:
        if not isinstance(raw, Mapping):
            continue
        bbox = _as_bbox(raw.get("bbox_norm"))
        if bbox is None:
            continue
        boxes.append(
            _Box(
                element_id=str(raw.get("element_id") or ""),
                type=str(raw.get("type") or ""),
                role=str(raw.get("role") or ""),
                bbox=bbox,
                tokens=_tokens(str(raw.get("text") or "")),
                area=max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1]),
            )
        )
    return boxes

@dataclass(slots=True)
class _Text:

    raw: str
    text: str = ""

@dataclass(slots=True)
class _Element:
    tag: str
    attrs: list[tuple[str, str | None]] = field(default_factory=list)
    children: list[Any] = field(default_factory=list)
    void: bool = False
    self_closed: bool = False
    bbox: Bbox | None = None
    source: str = ""
    element_id: str = ""
    element_ids: tuple[str, ...] = ()
    role: str = ""
    hint: str = ""

    @property
    def is_block(self) -> bool:
        return self.tag in _BLOCK or self.tag in _VISUAL

    def attr(self, name: str) -> str | None:
        for key, value in self.attrs:
            if key == name:
                return value
        return None

class _FragmentParser(HTMLParser):

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = _Element(tag="#root")
        self._stack: list[_Element] = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Element(tag=tag, attrs=list(attrs), void=tag in _VOID)
        self._stack[-1].children.append(node)
        if not node.void:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(
            _Element(tag=tag, attrs=list(attrs), void=True, self_closed=True)
        )

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        for depth in range(len(self._stack) - 1, 0, -1):
            if self._stack[depth].tag == tag:
                del self._stack[depth:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(_Text(raw=data, text=data))

    def handle_entityref(self, name):
        raw = f"&{name};"
        self._stack[-1].children.append(_Text(raw=raw, text=html_lib.unescape(raw)))

    def handle_charref(self, name):
        raw = f"&#{name};"
        self._stack[-1].children.append(_Text(raw=raw, text=html_lib.unescape(raw)))

    def handle_comment(self, data):
        self._stack[-1].children.append(_Text(raw=f"<!--{data}-->"))

    def handle_decl(self, decl):
        self._stack[-1].children.append(_Text(raw=f"<!{decl}>"))

    def handle_pi(self, data):
        self._stack[-1].children.append(_Text(raw=f"<?{data}>"))

def _render_attr(name: str, value: str | None) -> str:
    if value is None:
        return name
    return f'{name}="{html_lib.escape(value, quote=True)}"'

def _serialize(node: Any) -> str:
    if isinstance(node, _Text):
        return node.raw
    parts: list[str] = []
    if node.tag != "#root":
        rendered = " ".join(_render_attr(k, v) for k, v in node.attrs)
        separator = " " if rendered else ""
        if node.self_closed:
            return f"<{node.tag}{separator}{rendered} />"
        parts.append(f"<{node.tag}{separator}{rendered}>")
    parts.extend(_serialize(child) for child in node.children)
    if node.tag != "#root" and not node.void:
        parts.append(f"</{node.tag}>")
    return "".join(parts)

def _walk(node: _Element) -> Iterable[_Element]:

    for child in node.children:
        if isinstance(child, _Element):
            yield child
            yield from _walk(child)

def _outer_visuals(node: _Element, inside: bool = False) -> Iterable[_Element]:
    for child in node.children:
        if not isinstance(child, _Element):
            continue
        is_visual = child.tag in _VISUAL
        if is_visual and not inside:
            yield child
        yield from _outer_visuals(child, inside or is_visual)

def _node_text(node: Any) -> str:
    if isinstance(node, _Text):
        return node.text
    return " ".join(_node_text(child) for child in node.children)

def _strip_managed(node: _Element, boxes: list[_Box]) -> None:

    known = {box.element_id for box in boxes if box.element_id}
    for element in _walk(node):
        candidate = element.attr(ELEMENT_ID_ATTR)
        if candidate in known and element.attr(BBOX_SOURCE_ATTR) is None:
            element.hint = str(candidate)
        element.attrs = [(k, v) for k, v in element.attrs if k not in _MANAGED]

def _match_visuals(blocks: Sequence[_Element], boxes: list[_Box]) -> None:

    visuals = [box for box in boxes if box.type in {"image", "drawing"}]
    figures = [node for node in blocks if node.tag in _VISUAL]
    if not visuals or not figures:
        return

    adjudicados = {node.element_id for node in figures if node.bbox is not None}
    for box in visuals:
        if box.element_id and box.element_id in adjudicados:
            box.used = True

    pendientes = [node for node in figures if node.bbox is None]
    libres = [box for box in visuals if not box.used]
    if not pendientes or not libres:
        return

    if len(libres) == len(pendientes):
        for node, box in zip(pendientes, libres):
            node.bbox = box.bbox
            node.source = "visual-order"
            node.element_id = box.element_id
            node.role = box.role
            box.used = True
        return

    region = _union(box.bbox for box in libres)
    if region is None:
        return
    for node in pendientes:
        node.bbox = region
        node.source = "visual-region"

def _match_text(node: _Element, tokens: frozenset[str], boxes: Sequence[_Box]) -> None:
    text_boxes = [box for box in boxes if box.tokens]
    if not tokens or not text_boxes:
        return

    best: _Box | None = None
    best_key: tuple[float, float, float] | None = None
    for box in text_boxes:
        shared = len(tokens & box.tokens)
        if not shared:
            continue
        in_node = shared / len(tokens)
        if in_node < _CONTAINMENT:
            continue

        key = (-in_node, -(shared / len(box.tokens)), box.area)
        if best_key is None or key < best_key:
            best, best_key = box, key
    if best is not None:
        node.bbox = best.bbox
        node.source = "text"
        node.element_id = best.element_id
        node.role = best.role
        return

    covered = [
        box for box in text_boxes if len(tokens & box.tokens) / len(box.tokens) >= _COVERAGE
    ]
    union = _union(box.bbox for box in covered)
    if union is not None:
        node.bbox = union
        node.source = "text-union"
        node.element_ids = tuple(box.element_id for box in covered if box.element_id)

def _match_texts(blocks: Sequence[_Element], boxes: Sequence[_Box]) -> None:
    for node in blocks:
        if node.bbox is not None or node.tag in _VISUAL:
            continue
        _match_text(node, _tokens(_node_text(node)), boxes)

_EXACT = frozenset({"model-id", "text", "visual-order"})

def _fill_from_children(node: _Element) -> Bbox | None:

    boxes: list[Bbox] = []
    for child in node.children:
        if not isinstance(child, _Element):
            continue
        child_box = _fill_from_children(child)
        if child_box is not None:
            boxes.append(child_box)
    if node.is_block and boxes and node.source not in _EXACT:
        node.bbox = _union([*boxes, node.bbox] if node.bbox else boxes)
        if node.source != "text-union":
            node.source = "children"
    return node.bbox

def _fill_from_ancestors(node: _Element, inherited: Bbox | None) -> None:

    for child in node.children:
        if not isinstance(child, _Element):
            continue
        if child.bbox is None and child.is_block and inherited is not None:
            child.bbox = inherited
            child.source = "inherited"
        _fill_from_ancestors(child, child.bbox or inherited)

def _apply(
    node: _Element,
    *,
    page_width: float,
    page_height: float,
    decimals: int,
    outermost: bool = True,
) -> None:
    for child in node.children:
        if not isinstance(child, _Element):
            continue
        if child.bbox is not None and child.is_block:
            _write(
                child,
                page_width=page_width,
                page_height=page_height,
                decimals=decimals,
                with_page=outermost,
            )
            _apply(
                child,
                page_width=page_width,
                page_height=page_height,
                decimals=decimals,
                outermost=False,
            )
        else:
            _apply(
                child,
                page_width=page_width,
                page_height=page_height,
                decimals=decimals,
                outermost=outermost,
            )

def _write(
    node: _Element, *, page_width: float, page_height: float, decimals: int, with_page: bool
) -> None:
    if node.bbox is None:
        return
    x0, y0, x1, y1 = node.bbox
    node.attrs.append((BBOX_ATTR, _fmt_bbox(node.bbox, decimals)))
    if page_width > 0 and page_height > 0:
        absolute = (x0 * page_width, y0 * page_height, x1 * page_width, y1 * page_height)
        node.attrs.append((BBOX_ABS_ATTR, ",".join(_fmt(v, 2) for v in absolute)))
    node.attrs.append((BBOX_SOURCE_ATTR, node.source or "children"))
    if node.role:
        node.attrs.append((BBOX_ROLE_ATTR, node.role))
    if node.element_id:
        node.attrs.append((ELEMENT_ID_ATTR, node.element_id))
    elif node.element_ids:

        node.attrs.append((ELEMENT_IDS_ATTR, " ".join(node.element_ids)))
    if with_page:

        node.attrs.append((BBOX_SPACE_ATTR, "normalized"))
        if page_width > 0 and page_height > 0:
            node.attrs.append((PAGE_WIDTH_ATTR, _fmt(page_width, 2)))
            node.attrs.append((PAGE_HEIGHT_ATTR, _fmt(page_height, 2)))

def annotate_html_with_bboxes(
    html_fragment: str,
    elements: Sequence[Mapping[str, Any]] | None,
    *,
    page_width: float = 0.0,
    page_height: float = 0.0,
    decimals: int = 4,
) -> str:

    fragment = html_fragment or ""
    boxes = _inventory(elements)
    if not fragment.strip() or not boxes:
        return fragment

    parser = _FragmentParser()
    try:
        parser.feed(fragment)
        parser.close()
    except Exception:
        return fragment

    root = parser.root
    _strip_managed(root, boxes)

    blocks = [node for node in _walk(root) if node.is_block]
    if not blocks:
        return fragment

    by_id = {box.element_id: box for box in boxes if box.element_id}
    for node in blocks:
        box = by_id.get(node.hint)
        if box is not None:
            node.bbox, node.source = box.bbox, "model-id"
            node.element_id, node.role = box.element_id, box.role

    _match_visuals(list(_outer_visuals(root)), boxes)
    _match_texts(blocks, boxes)
    _fill_from_children(root)

    for child in root.children:
        if isinstance(child, _Element) and child.is_block and child.bbox is None:
            child.bbox, child.source = _FULL_PAGE, "page"

    _fill_from_ancestors(root, None)
    _apply(root, page_width=page_width, page_height=page_height, decimals=decimals)
    return _serialize(root)

def bboxes_in_html(html_fragment: str) -> list[dict[str, Any]]:

    parser = _FragmentParser()
    try:
        parser.feed(html_fragment or "")
        parser.close()
    except Exception:
        return []
    found: list[dict[str, Any]] = []
    for node in _walk(parser.root):
        raw = node.attr(BBOX_ATTR)
        if raw is None:
            continue
        bbox = _as_bbox(raw.split(","))
        if bbox is None:
            continue
        found.append(
            {
                "tag": node.tag,
                "bbox_norm": bbox,
                "source": node.attr(BBOX_SOURCE_ATTR) or "",
                "element_id": node.attr(ELEMENT_ID_ATTR) or "",
                "role": node.attr(BBOX_ROLE_ATTR) or "",
                "text": " ".join(_node_text(node).split()),
            }
        )
    return found

__all__ = [
    "BBOX_ABS_ATTR",
    "BBOX_ATTR",
    "BBOX_ROLE_ATTR",
    "BBOX_SOURCE_ATTR",
    "ELEMENT_ID_ATTR",
    "annotate_html_with_bboxes",
    "bboxes_in_html",
]
