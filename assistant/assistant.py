from langgraph.graph import StateGraph, END
from .state import AgentState, new_agent_state
from .nodes import (
    node_listen,
    node_analyze_semantics,
    node_process_visuals,
    node_refine_deictic_response,
    node_notify_user,
    node_user_decision,
    node_speak_description,
)
from .settings import settings
from .tools import hardware

workflow = StateGraph(AgentState)

workflow.add_node("listen", node_listen)
workflow.add_node("router", node_analyze_semantics)
workflow.add_node("vision_ai", node_process_visuals)
workflow.add_node("deictic_refine", node_refine_deictic_response)
workflow.add_node("notify", node_notify_user)
workflow.add_node("wait_for_user", node_user_decision)
workflow.add_node("tts", node_speak_description)

workflow.add_edge("listen", "router")

def _loop_enabled(state):
    return bool(state.get("loop_graph", False))

def router_logic(state):
    if state.get("awaiting_user_decision", False) and not state.get("user_requested_info", False):
        return "end"
    if state.get("router_tool_called", False):
        return "active"
    if _loop_enabled(state):
        return "ignore"
    return "end"

workflow.add_conditional_edges(
    "router",
    router_logic,
    {
        "active": "vision_ai",
        "ignore": "listen",
        "end": END,
    },
)

workflow.add_edge("vision_ai", "deictic_refine")
workflow.add_edge("deictic_refine", "notify")
workflow.add_edge("notify", "wait_for_user")

def wait_for_user_logic(state):
    if state.get("user_requested_info", False):
        return "speak"
    if _loop_enabled(state):
        return "ignore"
    return "end"

workflow.add_conditional_edges(
    "wait_for_user",
    wait_for_user_logic,
    {
        "speak": "tts",
        "ignore": "listen",
        "end": END,
    },
)

def tts_logic(state):
    if _loop_enabled(state):
        return "listen"
    return "end"

workflow.add_conditional_edges(
    "tts",
    tts_logic,
    {
        "listen": "listen",
        "end": END,
    },
)

workflow.set_entry_point("listen")
app = workflow.compile()

_PER_TURN_KEYS = (
    "user_requested_info",
    "loop_graph",
    "router_tool_called",
    "visual_focus",
    "visual_type",
    "detail_level",
    "deictic_expression",
    "router_reason",
    "precomputed_used",
    "precomputed_source",
)

def run_assistant():
    state = new_agent_state()
    print("Asistente iniciado. Escribe 'salir' para terminar.")

    while True:
        text = hardware.capture_audio_segment().strip()
        if text.lower() in {"salir", "exit", "quit"}:
            break
        persistent_buffer = list(state.get("transcript_buffer", []))
        candidate_buffer = list(persistent_buffer)
        if text and text != ".":
            candidate_buffer.append(text)
            if len(candidate_buffer) > settings.window_size:
                candidate_buffer = candidate_buffer[-settings.window_size:]

        defaults = new_agent_state()
        for key in _PER_TURN_KEYS:
            state[key] = defaults[key]
        state["transcript_buffer"] = candidate_buffer
        state["current_context_text"] = " ".join(candidate_buffer)
        state = app.invoke(state)

        trigger_visual = bool(state.get("router_tool_called", False))
        if trigger_visual:
            committed_buffer = persistent_buffer[-settings.window_size:]
        else:
            committed_buffer = candidate_buffer
        state["transcript_buffer"] = committed_buffer
        state["current_context_text"] = " ".join(committed_buffer)