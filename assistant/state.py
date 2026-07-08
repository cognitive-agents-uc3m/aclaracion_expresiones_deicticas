from typing import Any, Dict, List, Optional, TypedDict

class AgentState(TypedDict):
    transcript_buffer: List[str]
    current_context_text: str
    router_tool_called: bool
    visual_focus: Optional[str]
    visual_type: Optional[str]
    detail_level: Optional[str]
    deictic_expression: Optional[str]
    router_reason: Optional[str]
    uploaded_image: Optional[str]
    uploaded_pdf: Optional[str]
    current_slide_index: int
    current_slide_count: int
    current_frame: Optional[str]
    generated_description: Optional[str]
    precomputed_used: bool
    precomputed_source: Optional[str]
    pointer_x_norm: Optional[float]
    pointer_y_norm: Optional[float]
    pointer_ts_ms: Optional[int]
    pointing_element_hint: Optional[str]
    user_requested_info: bool
    awaiting_user_decision: bool
    loop_graph: bool

def new_agent_state() -> Dict[str, Any]:
    return {
        "transcript_buffer": [],
        "current_context_text": "",
        "router_tool_called": False,
        "visual_focus": None,
        "visual_type": None,
        "detail_level": None,
        "deictic_expression": None,
        "router_reason": None,
        "uploaded_image": None,
        "uploaded_pdf": None,
        "current_slide_index": 0,
        "current_slide_count": 0,
        "current_frame": None,
        "generated_description": None,
        "precomputed_used": False,
        "precomputed_source": None,
        "pointer_x_norm": None,
        "pointer_y_norm": None,
        "pointer_ts_ms": None,
        "pointing_element_hint": None,
        "user_requested_info": False,
        "awaiting_user_decision": False,
        "loop_graph": False,
    }

def format_router_info(state: Dict[str, Any]) -> str:
    visual = bool(state.get("router_tool_called", False))
    reason = (state.get("router_reason") or "Sin analisis").strip()
    focus = (state.get("visual_focus") or "-").strip() or "-"
    deictic = (state.get("deictic_expression") or "-").strip() or "-"
    source = (state.get("precomputed_source") or "-").strip() or "-"
    precomputed_used = bool(state.get("precomputed_used", False))
    return (
        f"Visual: {visual}\n"
        f"Razon: {reason}\n"
        f"Foco: {focus}\n"
        f"Deixis: {deictic}\n"
        f"Precomputado: {precomputed_used}\n"
        f"Fuente: {source}"
    )