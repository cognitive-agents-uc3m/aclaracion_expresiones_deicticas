import base64
import logging
import os
import re
import time
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from .settings import settings
from .slide_knowledge import slide_knowledge_store, slide_precompute_service
from .slide_layout import extract_slide_elements_from_page, pick_element_for_point, format_elements_inventory
from .state import AgentState
from .tools import hardware

logger = logging.getLogger(__name__)

router_llm = None
router_llm_with_tools = None
vision_llm = None

def _build_chat_ollama(model_name: str, temperature: float, timeout_seconds: float | None = None):
    kwargs = {
        "model": model_name,
        "temperature": temperature,
        "base_url": settings.ollama_base_url,
        "num_gpu": settings.ollama_num_gpu,
    }
    try:
        if timeout_seconds is not None:
            kwargs["client_kwargs"] = {"timeout": timeout_seconds}
        return ChatOllama(**kwargs)
    except TypeError:
        kwargs.pop("client_kwargs", None)
        return ChatOllama(**kwargs)


def _build_chat_gemini(model_name: str, temperature: float):
    try:
        from langchain_google_vertexai import ChatVertexAI
    except ImportError as exc:
        raise ImportError(
            "Para usar Gemini instala: pip install langchain-google-vertexai"
        ) from exc
    kwargs: dict = {"model_name": model_name, "temperature": temperature}
    if settings.gcp_project:
        kwargs["project"] = settings.gcp_project
    if settings.gcp_location:
        kwargs["location"] = settings.gcp_location
    return ChatVertexAI(**kwargs)

VISION_AI_TOOL = {
    "type": "function",
    "function": {
        "name": "vision_ai",
        "description": (
            "Solicita analisis visual cuando el profesor hace una referencia clara "
            "a una diapositiva, grafica, imagen, pantalla o elemento visible que "
            "merece ser descrito al usuario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "visual_focus": {
                    "type": "string",
                    "description": (
                        "Elemento visual concreto al que se refiere el orador. "
                        "Ejemplos: titulo, grafica de barras, columna izquierda, "
                        "parte superior derecha. Usa cadena vacia si no hay foco claro."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "Motivo breve por el que compensa lanzar el analisis visual.",
                },
                "visual_type": {
                    "type": "string",
                    "enum": ["desconocido", "texto_simple", "diagrama", "grafica", "tabla", "foto"],
                    "description": "Tipo de elemento visual principal al que apunta el orador.",
                },
                "detail_level": {
                    "type": "string",
                    "enum": ["short", "medium", "deep"],
                    "description": "Nivel de detalle recomendado para la respuesta accesible final.",
                },
            },
            "required": ["reason"],
        },
    },
}

if not settings.is_simulation:
    try:
        if settings.llm_provider == "gemini":
            router_llm = _build_chat_gemini(
                model_name=settings.gemini_router_model_name,
                temperature=0,
            )
            vision_llm = _build_chat_gemini(
                model_name=settings.gemini_vision_model_name,
                temperature=0.0,
            )
            logger.info("LLM provider: Gemini (Vertex AI / ADC)")
        else:
            router_llm = _build_chat_ollama(
                model_name=settings.router_model_name,
                temperature=0,
                timeout_seconds=settings.llm_request_timeout_seconds,
            )
            vision_llm = _build_chat_ollama(
                model_name=settings.vision_model_name,
                temperature=0.0,
                timeout_seconds=settings.llm_request_timeout_seconds,
            )
            logger.info("LLM provider: Ollama")
        router_llm_with_tools = router_llm.bind_tools([VISION_AI_TOOL])
    except Exception as ex:
        logger.error("Error inicializando LLM (%s): %s", settings.llm_provider, ex)

def encode_image(image_path: str) -> str | None:
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as ex:
        logger.error("Error cargando imagen: %s", ex)
        return None

def guess_mime_type(image_path: str) -> str:
    ext = os.path.splitext((image_path or "").lower())[1]
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    return "image/png"

def _safe_summary(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return "Sin resumen."
    first = cleaned.split(".")[0].strip()
    if first:
        return first[:240]
    return cleaned[:240]

def _sanitize_vision_output(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\b(\w+)(?:\s+\1\b){2,}", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\w+\s+\w+)(?:\s+\1\b){2,}", r"\1", cleaned, flags=re.IGNORECASE)
    return cleaned

DEICTIC_PATTERNS = (
    r"\baqui\b",
    r"\besto\b",
    r"\besta\b",
    r"\beste\b",
    r"\bese\b",
    r"\besa\b",
    r"\bvemos\b",
    r"\bmirad\b",
    r"\bmira\b",
    r"\barriba\b",
    r"\babajo\b",
    r"\bizquierda\b",
    r"\bderecha\b",
    r"\bse puede ver\b",
    r"\bver\b",
)

def _extract_deictic_expression(text: str) -> str:
    lowered = (text or "").lower()
    for pattern in DEICTIC_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0)
    return ""

def _normalize_visual_type(value: str) -> str:
    allowed = {"desconocido", "texto_simple", "diagrama", "grafica", "tabla", "foto"}
    candidate = (value or "").strip().lower()
    return candidate if candidate in allowed else "desconocido"

def _normalize_detail_level(value: str) -> str:
    allowed = {"short", "medium", "deep"}
    candidate = (value or "").strip().lower()
    return candidate if candidate in allowed else ""

def _infer_visual_type(context: str, focus: str) -> str:
    text = f"{context or ''} {focus or ''}".lower()
    if any(t in text for t in ("grafica", "gráfico", "barra", "linea", "línea", "eje", "tarta", "pastel")):
        return "grafica"
    if any(t in text for t in ("diagrama", "flujo", "proceso", "flecha", "bloque", "ciclo", "esquema")):
        return "diagrama"
    if any(t in text for t in ("tabla", "fila", "columna", "celda", "matriz")):
        return "tabla"
    if any(t in text for t in ("foto", "imagen", "icono", "ilustracion", "ilustración")):
        return "foto"
    return "texto_simple"

def _build_vision_llm():
    if settings.llm_provider == "gemini":
        return _build_chat_gemini(
            model_name=settings.gemini_vision_model_name,
            temperature=0.0,
        )
    return _build_chat_ollama(
        model_name=settings.vision_model_name,
        temperature=0.0,
        timeout_seconds=settings.precompute_slide_timeout_seconds,
    )

def _build_vision_message(prompt_text: str, img_base64: str, mime: str) -> HumanMessage:
    if settings.llm_provider == "gemini":
        image_part = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_base64}"}}
    else:
        image_part = {"type": "image_url", "image_url": f"data:{mime};base64,{img_base64}"}
    return HumanMessage(content=[{"type": "text", "text": prompt_text}, image_part])

def _is_transient_vision_error(ex: Exception) -> bool:
    text = f"{type(ex).__name__}: {ex}".lower()
    transient_tokens = (
        "timeout", "timed out", "readtimeout", "connection",
        "temporarily unavailable", "service unavailable", "overloaded",
    )
    return any(token in text for token in transient_tokens)

def _invoke_vision_with_retries(message, slide_index: int, slide_count: int):
    attempts = max(1, int(settings.precompute_retry_attempts))
    base_backoff = max(0.0, float(settings.precompute_retry_backoff_seconds))
    last_ex = None

    for attempt in range(1, attempts + 1):
        try:
            llm = _build_vision_llm()
            return llm.invoke([message])
        except Exception as ex:
            last_ex = ex
            transient = _is_transient_vision_error(ex)
            logger.warning(
                "Vision fallo slide %d/%d intento %d/%d: %s: %s",
                slide_index + 1, slide_count, attempt, attempts, type(ex).__name__, ex,
            )
            if (not transient) or attempt >= attempts:
                break
            sleep_s = base_backoff * attempt
            if sleep_s > 0:
                time.sleep(sleep_s)

    raise RuntimeError(f"Vision fallo tras {attempts} intentos: {type(last_ex).__name__}: {last_ex}")

def generate_slide_knowledge_for_image(image_path: str, slide_index: int, slide_count: int):
    if settings.is_simulation:
        detailed = (
            f"[Vision General] Simulacion de slide {slide_index + 1}/{slide_count}. "
            "[Mapa Espacial Macro] Franja superior de cabecera, bloque central dominante y zona inferior secundaria. "
            "[Mapa Espacial Detallado] Recorrido de arriba a abajo: esquina superior izquierda para titulo, "
            "zona superior central para subtitulo, esquina superior derecha para fecha, centro para contenido principal. "
            "[Texto Visible] no legible. "
            "[Elementos Visuales] ninguno. "
            "[Lectura Guiada] Avanza de izquierda a derecha en cada franja y luego desciende al siguiente bloque."
        )
        return detailed, _safe_summary(detailed)

    img_base64 = encode_image(image_path)
    if not img_base64:
        raise RuntimeError("No se pudo leer la imagen para preprocesado.")
    mime = guess_mime_type(image_path)

    profile = settings.ACTIVE_SLIDE_PROMPT_PROFILE
    template = settings.SLIDE_DESCRIPTION_PROMPT_TEMPLATES[profile]
    prompt_text = template.format(SLIDE_NUMBER=slide_index + 1, SLIDE_COUNT=slide_count)

    msg = _build_vision_message(prompt_text, img_base64, mime)
    response = _invoke_vision_with_retries(msg, slide_index=slide_index, slide_count=slide_count)
    detailed = _sanitize_vision_output((response.content or "").strip())
    if not detailed:
        raise RuntimeError("El modelo de vision devolvio salida vacia.")
    return detailed, _safe_summary(detailed)

def _compose_response_from_precomputed(
    detailed_description: str,
    summary: str,
    context: str,
    focus: str,
    slide_index: int,
    slide_count: int,
) -> str:
    focus_text = focus if focus else "sin foco explicito"
    context_text = context.strip() if context else "sin contexto adicional"
    return (
        f"Diapositiva {slide_index + 1}/{slide_count}. "
        f"Contexto del orador: {context_text}. "
        f"Foco detectado: {focus_text}. "
        f"Resumen breve: {summary}. "
        f"Descripcion espacial detallada: {detailed_description}"
    )

def node_listen(state: AgentState) -> AgentState:
    buffer = state.get("transcript_buffer", [])
    if len(buffer) > settings.window_size:
        buffer = buffer[-settings.window_size:]
    full_context = " ".join(buffer)
    logger.info("[Oido]: ... %s ...", full_context)
    return {
        "transcript_buffer": buffer,
        "current_context_text": full_context,
        "user_requested_info": False,
    }

def node_analyze_semantics(state: AgentState) -> AgentState:
    text = state["current_context_text"]
    deictic_expression = _extract_deictic_expression(text)
    visual_type = "desconocido"
    detail_level = ""

    if settings.is_simulation:
        keywords = ["aqui", "esta", "esto", "mirad", "vemos", "grafica", "imagen", "arriba"]
        tool_called = any(word in text.lower() for word in keywords)
        visual_focus = ""
        reason = "Simulacion"
        if tool_called:
            visual_type = _infer_visual_type(text, visual_focus)
            detail_level = ""
    else:
        try:
            messages = [
                (
                    "system",
                    """Eres el router de un asistente para personas no videntes en clase.
                    Decide si merece la pena lanzar la herramienta `vision_ai`.

                    Usa `vision_ai` solo cuando el audio contenga una referencia visual clara o altamente probable:
                    - el orador señala algo visible
                    - menciona una diapositiva, grafica, imagen, tabla, pantalla o pizarra
                    - hay una referencia deictica como "aqui", "esto", "vemos", "arriba", "a la derecha", "se puede ver"
                    - hay marcadores de atencion visual aunque no haya deixis explicita,
                      por ejemplo: "como puedes ver", "como podeis observar", "fijate", "observa"

                    No uses herramientas si el texto es puramente verbal, ambiguo o no aporta valor visual.""",
                ),
                ("human", text),
            ]

            if router_llm_with_tools is None or router_llm is None:
                raise RuntimeError("router_llm no inicializado")

            try:
                response = router_llm_with_tools.invoke(messages)
                tool_call = next(
                    (call for call in response.tool_calls if call.get("name") == "vision_ai"),
                    None,
                )
                if tool_call:
                    args = tool_call.get("args") or {}
                    tool_called = True
                    visual_focus = str(args.get("visual_focus") or "").strip()
                    reason = str(args.get("reason") or "El modelo ha solicitado analisis visual.").strip()
                    visual_type = _normalize_visual_type(str(args.get("visual_type") or ""))
                    detail_level = _normalize_detail_level(str(args.get("detail_level") or ""))
                else:
                    tool_called = False
                    visual_focus = ""
                    reason = (response.content or "Sin analisis visual.").strip()
            except Exception as tool_ex:
                err_msg = f"{type(tool_ex).__name__}: {tool_ex}"
                if "does not support tools" not in err_msg.lower():
                    raise

                fallback_response = router_llm.invoke(
                    [
                        (
                            "system",
                            "Decide si hay que activar análisis visual.\n"
                            "Responde con UNICA y EXACTAMENTE una de estas dos formas:\n"
                            "CALL_VISION_AI|<visual_focus>|<motivo>\n"
                            "SKIP|<motivo>",
                        ),
                        ("human", text),
                    ]
                )
                raw = (fallback_response.content or "").strip()
                if raw.startswith("CALL_VISION_AI|"):
                    parts = raw.split("|", 2)
                    tool_called = True
                    visual_focus = parts[1].strip() if len(parts) > 1 else ""
                    reason = parts[2].strip() if len(parts) > 2 else "Fallback textual."
                elif raw.startswith("SKIP|"):
                    parts = raw.split("|", 1)
                    tool_called = False
                    visual_focus = ""
                    reason = parts[1].strip() if len(parts) > 1 else "Sin analisis visual."
                else:
                    tool_called = False
                    visual_focus = ""
                    reason = raw or "Sin analisis visual."
        except Exception as ex:
            err_msg = f"{type(ex).__name__}: {ex}"
            logger.error("[Router] Error final: %s", err_msg)
            tool_called = False
            visual_focus = ""
            reason = f"Error LLM: {err_msg[:220]}"

    logger.info(
        "[Router] vision_ai=%s | focus='%s' | type='%s' | detail='%s' | deixis='%s' | reason='%s'",
        tool_called, visual_focus or "-", visual_type, detail_level or "-",
        deictic_expression or "-", reason or "-",
    )
    if tool_called:
        if visual_type in {"", "desconocido"}:
            visual_type = _infer_visual_type(text, visual_focus)
        if not detail_level:
            detail_level = ""
    else:
        visual_type = "desconocido"
        detail_level = ""
    return {
        "router_tool_called": tool_called,
        "visual_focus": visual_focus,
        "visual_type": visual_type,
        "detail_level": detail_level,
        "deictic_expression": deictic_expression,
        "router_reason": reason,
    }

def node_process_visuals(state: AgentState) -> AgentState:
    context = state["current_context_text"]
    uploaded = state.get("uploaded_image")
    uploaded_pdf = state.get("uploaded_pdf")
    slide_index = int(state.get("current_slide_index", 0))
    slide_count = int(state.get("current_slide_count", 0))
    focus = (state.get("visual_focus") or "").strip()
    pointer_x = state.get("pointer_x_norm")
    pointer_y = state.get("pointer_y_norm")

    pointing_hint = ""
    inventory_text = ""
    if uploaded_pdf and slide_count > 0 and pointer_x is not None and pointer_y is not None:
        try:
            _, record = slide_knowledge_store.get_slide_by_pdf(uploaded_pdf, slide_index)
            elements = (record or {}).get("elements") or []
            if not elements:
                import fitz
                with fitz.open(uploaded_pdf) as doc:
                    page = doc.load_page(slide_index)
                    layout = extract_slide_elements_from_page(page)
                    elements = layout.get("elements") or []
            inventory_text = format_elements_inventory(elements)
            picked = pick_element_for_point(elements, float(pointer_x), float(pointer_y))
            if picked:
                bbox = picked.get("bbox_norm") or (0, 0, 0, 0)
                eid = picked.get("element_id") or "-"
                etype = picked.get("type") or "desconocido"
                role = (picked.get("role") or "").strip()
                text_snippet = " ".join((picked.get("text") or "").split()).strip()
                if len(text_snippet) > 280:
                    text_snippet = text_snippet[:280] + "..."
                pointing_hint = (
                    f"id={eid} tipo={etype} "
                    + (f"rol={role} " if role else "")
                    + f"bbox_norm={bbox} "
                    + (f"texto='{text_snippet}'" if text_snippet else "")
                ).strip()
        except Exception as ex:
            logger.debug("Error resolviendo elemento apuntado: %s", ex)
            pointing_hint = ""
            inventory_text = ""

    image_path = uploaded or "placeholder.jpg"

    if settings.use_precomputed_descriptions and uploaded_pdf and slide_count > 0:
        _, record = slide_knowledge_store.get_slide_by_pdf(uploaded_pdf, slide_index)
        if record and record.get("status") == "ready":
            detailed = (record.get("detailed_description") or "").strip()
            if "[Inventario por bounding boxes]" not in detailed:
                try:
                    elements = (record.get("elements") or []) if isinstance(record, dict) else []
                    if not elements:
                        import fitz
                        with fitz.open(uploaded_pdf) as doc:
                            page = doc.load_page(slide_index)
                            layout = extract_slide_elements_from_page(page)
                            elements = layout.get("elements") or []
                    extra = format_elements_inventory(elements)
                    if extra:
                        detailed = f"{detailed}\n\n{extra}".strip()
                except Exception as ex:
                    logger.debug("Error ampliando inventario de diapositiva: %s", ex)
            summary = (record.get("summary") or "").strip() or _safe_summary(detailed)
            description = _compose_response_from_precomputed(
                detailed_description=detailed,
                summary=summary,
                context=context,
                focus=focus,
                slide_index=slide_index,
                slide_count=slide_count,
            )
            return {
                "current_frame": image_path,
                "generated_description": description,
                "precomputed_used": True,
                "precomputed_source": f"slide:{slide_index + 1}/{slide_count}",
                "pointing_element_hint": pointing_hint or None,
            }

        if settings.precompute_on_upload:
            slide_precompute_service.enqueue_pdf(uploaded_pdf, slide_count, mode="all")
        preload_status = slide_knowledge_store.deck_status_text(uploaded_pdf)
        return {
            "current_frame": image_path,
            "generated_description": (
                f"La descripcion precomputada de la diapositiva {slide_index + 1}/{slide_count} "
                f"aun no esta lista. {preload_status}"
            ),
            "precomputed_used": False,
            "precomputed_source": None,
            "pointing_element_hint": pointing_hint or None,
        }

    try:
        detailed, summary = generate_slide_knowledge_for_image(
            image_path=image_path,
            slide_index=slide_index,
            slide_count=max(1, slide_count),
        )
        detailed = (detailed or "").strip()
        if uploaded_pdf and slide_count > 0 and not inventory_text:
            try:
                import fitz
                with fitz.open(uploaded_pdf) as doc:
                    page = doc.load_page(slide_index)
                    layout = extract_slide_elements_from_page(page)
                    inventory_text = format_elements_inventory(layout.get("elements") or [])
            except Exception as ex:
                logger.debug("Error generando inventario en-vivo: %s", ex)
                inventory_text = ""
        if inventory_text and "[Inventario por bounding boxes]" not in detailed:
            detailed = f"{detailed}\n\n{inventory_text}".strip()
        description = _compose_response_from_precomputed(
            detailed_description=detailed,
            summary=summary,
            context=context,
            focus=focus,
            slide_index=slide_index,
            slide_count=max(1, slide_count),
        )
    except Exception as ex:
        description = f"Error procesando vision: {ex}"

    return {
        "current_frame": image_path,
        "generated_description": description,
        "precomputed_used": False,
        "precomputed_source": None,
        "pointing_element_hint": pointing_hint or None,
    }

def node_notify_user(state: AgentState) -> AgentState:
    hardware.trigger_haptic_feedback()
    return {}

def node_refine_deictic_response(state: AgentState) -> AgentState:
    description = (state.get("generated_description") or "").strip()
    if not description:
        return {}

    deictic_expression = (state.get("deictic_expression") or "").strip()
    context = (state.get("current_context_text") or "").strip()
    focus = (state.get("visual_focus") or "").strip()
    pointing = (state.get("pointing_element_hint") or "").strip()
    deictic_text = deictic_expression or "sin expresion deictica explicita"


    style_rule = "Una sola frase. Máximo 20 palabras. Solo el dato esencial, sin explicaciones adicionales."

    if settings.is_simulation:
        refined = (
            f"Referencia: '{deictic_text}'. Foco: {focus or 'sin foco explicito'}."
            f" {description[:200]}"
        )
        return {"generated_description": refined}

    if router_llm is None:
        return {"generated_description": description[:300]}

    system_prompt = (
        "Eres un asistente accesible para estudiantes ciegos.\n\n"
        "Tu tarea: describir el elemento visual al que apunta el orador de forma directa y útil.\n\n"
        "PROHIBIDO en la respuesta:\n"
        "- Frases de resolución deíctica: '\"aquí\" se refiere a', 'la expresión apunta a', 'el orador señala que', 'esto hace referencia a', 'cuando dice X significa'.\n"
        "- Prefacios: 'Se puede ver', 'En la diapositiva', 'Observamos', 'La imagen muestra', 'Podemos ver'.\n"
        "- Verbalizar el razonamiento interno ni explicar el proceso.\n\n"
        "OBLIGATORIO: empieza la respuesta directamente con el nombre del elemento y su información útil.\n\n"
        "Razonamiento interno (solo para ti, no aparece en la respuesta):\n"
        "- ¿Qué elemento señala el orador?\n"
        "- ¿Cuál es su función o dato más relevante?\n"
        "- Si hay ambigüedad, elige el elemento más probable sin mencionarlo.\n\n"
        f"Regla de estilo: {style_rule}\n\nResponde en español."
    )
    human_prompt = (
        f"Expresion deictica detectada:\n{deictic_text}\n\n"
        f"Foco visual detectado:\n{focus or 'sin foco explicito'}\n\n"
        f"Elemento apuntado por el profesor (si disponible):\n{pointing or 'sin puntero / sin elemento resuelto'}\n\n"
        f"Frase del orador:\n{context or 'sin contexto'}\n\n"
        f"Descripcion visual de apoyo:\n{description}"
    )

    try:
        response = router_llm.invoke([("system", system_prompt), ("human", human_prompt)])
        refined = (response.content or "").strip()
        if refined:
            return {"generated_description": refined}
    except Exception as ex:
        logger.error("[Refine] Error refinando respuesta deictica: %s: %s", type(ex).__name__, ex)

    return {"generated_description": description[:300]}

def node_user_decision(state: AgentState) -> AgentState:
    requested = bool(state.get("user_requested_info", False))
    return {"user_requested_info": requested}

def node_speak_description(state: AgentState) -> AgentState:
    hardware.speak_text(state["generated_description"])
    return {}