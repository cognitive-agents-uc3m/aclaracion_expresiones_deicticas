
import html as html_lib
import logging
import os
import re
import time
from typing import Tuple
import fitz
from .settings import settings

logger = logging.getLogger(__name__)

SLIDE_HTML_PROMPT = """\
Eres un experto en accesibilidad web (WCAG 2.1) especializado en la \
conversión de material docente universitario a HTML semántico para \
lectores de pantalla.

El PDF adjunto contiene únicamente la diapositiva {SLIDE_NUMBER} de {SLIDE_COUNT} \
de una presentación. Convierte esa diapositiva en un FRAGMENTO de HTML \
completamente accesible, semántico y fiel al contenido original. Preserva toda \
la información educativa sin omisiones ni simplificaciones. El resultado debe \
ser totalmente usable por un estudiante ciego que use lector de pantalla.

El fragmento se insertará dentro del <main> de un documento ya existente: \
PROHIBIDO generar <!DOCTYPE>, <html>, <head>, <body>, <style>, <script> o skip-links.

<reglas_fidelidad>
1. NO inventes, añadas ni interpoles información que no esté explícitamente en la diapositiva.
2. Reproduce el texto fielmente; no parafrasees ni resumas.
3. Tu labor es ESTRUCTURAR y REPRESENTAR, no interpretar ni expandir.
4. Para elementos no textuales (imágenes, diagramas, fórmulas): descríbelos basándote \
   únicamente en lo que aparece en la diapositiva.
5. Si algo no es legible, indícalo con <p class="nota-accesibilidad"> en lugar de inventar.
</reglas_fidelidad>

<estructura>
- Devuelve una única <section> raíz con aria-labelledby apuntando al id de su encabezado:
    <section aria-labelledby="slide-{SLIDE_NUMBER}-titulo">
      <h2 id="slide-{SLIDE_NUMBER}-titulo">Título de la diapositiva</h2>
      [resto del contenido]
    </section>
- Si la diapositiva no tiene título visible, redacta un encabezado breve que \
  describa su contenido. Encabezados genéricos como "Continuación", "Más información" \
  u "Otros" están PROHIBIDOS.
- Jerarquía de encabezados sin saltos dentro del fragmento (h2 > h3 > h4, nunca h2 → h4).
- El HTML generado debe ser válido: todas las etiquetas correctamente cerradas, \
  atributos con valores entre comillas, sin atributos duplicados. \
  Los lectores de pantalla dependen de un árbol DOM bien formado (WCAG 4.1.2).
- PROHIBIDO elementos de presentación pura: <b>, <i>, <center>, <font>.
- PROHIBIDO el atributo style="" en cualquier elemento. Usa clases con nombre \
  descriptivo si necesitas marcar un rol visual (.nota-accesibilidad, .destacado, etc.).
- Elementos decorativos sin valor informativo (número de diapositiva, logos, \
  iconos puramente visuales) deben llevar aria-hidden="true".
- Si un fragmento de texto está en un idioma distinto al español, añade el atributo lang \
  en el elemento que lo contiene: <span lang="en">software engineering</span>. \
  Aplica a términos técnicos en inglés, expresiones latinas o cualquier otro idioma.
</estructura>

<secuencia>
- Si la diapositiva tiene columnas paralelas (dos o más bloques de texto en horizontal), \
  aplánalas en un único flujo lineal que siga el orden lógico de lectura \
  (generalmente: columna izquierda completa, luego columna derecha; o fila a fila si es una tabla de conceptos).
- El HTML debe leerse de arriba a abajo en el orden correcto sin navegación visual.
- Recuadros laterales y notas al margen se insertan en el flujo principal \
  en el punto donde aparecen: dentro de <aside> si son complementarios, \
  o dentro de <div> con clase descriptiva si forman parte del contenido principal.
</secuencia>

<tablas>
- <table> con <caption> descriptivo
- <thead> y <tbody> según corresponda
- <th scope="col"> en cabeceras de columna, <th scope="row"> en cabeceras de fila
- Celdas vacías de cabecera llevan scope="col" igualmente
</tablas>

<imagenes>
- <figure> + <figcaption> para cada elemento visual
- PROHIBIDO <img src="data:..."> o imágenes en base64. \
  Si es un diagrama, usa texto descriptivo, listas, tablas o código (PlantUML) \
  dentro del <figure>. Omite el <img> completamente.
- Si la imagen es decorativa o ilegible, incluye dentro del <figure> un \
  <p class="nota-accesibilidad"> explicando el motivo, antes del <figcaption>.
- Las fórmulas matemáticas se representan en MathML o en texto descriptivo legible.
- Si excepcionalmente se genera un <img>, incluye siempre el atributo alt (WCAG 1.1.1).
</imagenes>

<listas>
- Cualquier conjunto de ítems del mismo tipo (requisitos, ejemplos, pasos, opciones, \
  conceptos con icono) → <ul><li> o <ol><li>. NUNCA <div> o <span> genéricos.
- Grupos de término + definición (propiedades, atributos, estados, glosarios) → <dl>.
- Columnas o grids visuales de ítems equivalentes se convierten en listas semánticas, \
  independientemente de su disposición visual en la diapositiva.
</listas>

<color>
- PROHIBIDO usar el color como único indicador de información. \
  Añade siempre un indicador textual explícito, por ejemplo: \
  <li><strong>(Correcta)</strong> Texto de la opción</li>. \
  Aplica a: respuestas correctas, clasificaciones, alertas, estados.
</color>

Responde ÚNICAMENTE con el fragmento HTML, sin explicaciones ni bloques markdown.\
"""

_TAG_RE = re.compile(r"<[^>]+>")

def limpiar_html(texto: str) -> str:
    texto = (texto or "").strip()
    if texto.startswith("```html"):
        texto = texto[7:]
    elif texto.startswith("```"):
        texto = texto[3:]
    if texto.endswith("```"):
        texto = texto[:-3]
    return texto.strip()


def html_to_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    text = html_lib.unescape(text)
    return " ".join(text.split())


def _summary_from_html(html: str) -> str:
    cleaned = html_to_text(html)
    if not cleaned:
        return "Sin resumen."
    first = cleaned.split(".")[0].strip()
    return (first or cleaned)[:240]

def _is_transient_error(ex: Exception) -> bool:
    text = f"{type(ex).__name__}: {ex}".lower()
    transient_tokens = (
        "timeout", "timed out", "readtimeout", "connection",
        "temporarily unavailable", "service unavailable", "overloaded",
        "resource exhausted", "deadline exceeded", "429", "503",
    )
    return any(token in text for token in transient_tokens)

def _build_genai_client():
    from google import genai

    project = (
        (settings.gcp_project or "").strip()
        or os.getenv("GCP_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )
    if not project:
        try:
            import google.auth
            _, project = google.auth.default()
        except Exception:
            project = None

    location = os.getenv("GCP_LOCATION", "").strip() or (settings.gcp_location or "").strip()
    kwargs: dict = {"vertexai": True}
    if project:
        kwargs["project"] = project
    if location:
        kwargs["location"] = location
    return genai.Client(**kwargs)

def _extract_page_pdf_bytes(doc: "fitz.Document", slide_index: int) -> bytes:
    single = fitz.open()
    try:
        single.insert_pdf(doc, from_page=slide_index, to_page=slide_index)
        return single.tobytes()
    finally:
        single.close()

def generate_slide_html_for_page(doc: "fitz.Document", slide_index: int, slide_count: int) -> Tuple[str, str]:
    if settings.is_simulation:
        html = (
            f'<section aria-labelledby="slide-{slide_index + 1}-titulo">'
            f'<h2 id="slide-{slide_index + 1}-titulo">Simulacion de diapositiva '
            f'{slide_index + 1} de {slide_count}</h2>'
            "<p>Contenido HTML simulado.</p></section>"
        )
        return html, _summary_from_html(html)

    from google.genai import types

    pdf_bytes = _extract_page_pdf_bytes(doc, slide_index)
    prompt = SLIDE_HTML_PROMPT.format(SLIDE_NUMBER=slide_index + 1, SLIDE_COUNT=slide_count)
    contents = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt]

    attempts = max(1, int(settings.precompute_retry_attempts))
    base_backoff = max(0.0, float(settings.precompute_retry_backoff_seconds))
    last_ex = None

    for attempt in range(1, attempts + 1):
        try:
            client = _build_genai_client()
            response = client.models.generate_content(
                model=settings.slide_html_model,
                contents=contents,
            )
            html = limpiar_html(response.text or "")
            if not html:
                raise RuntimeError("El modelo devolvio HTML vacio.")
            return html, _summary_from_html(html)
        except Exception as ex:
            last_ex = ex
            logger.warning(
                "HTML fallo slide %d/%d intento %d/%d: %s: %s",
                slide_index + 1, slide_count, attempt, attempts, type(ex).__name__, ex,
            )
            if (not _is_transient_error(ex)) or attempt >= attempts:
                break
            sleep_s = base_backoff * attempt
            if sleep_s > 0:
                time.sleep(sleep_s)

    raise RuntimeError(
        f"Generacion HTML fallo tras {attempts} intentos: {type(last_ex).__name__}: {last_ex}"
    )