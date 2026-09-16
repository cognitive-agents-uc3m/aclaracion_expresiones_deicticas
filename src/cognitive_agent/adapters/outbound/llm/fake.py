from __future__ import annotations

import re
import threading
from .base import ChatResponse

_SLIDE = re.compile(r"Diapositiva actual:\s*(\d+)", re.IGNORECASE)
_EXPRESSION = re.compile(r"Expresion deictica detectada:\s*\n(.+)", re.IGNORECASE)

class FakeChatModel:

    name = "fake"

    def __init__(
        self,
        *,
        model_id: str = "fake-1",
        responses: list[str] | None = None,
        fail_times: int = 0,
        delay_seconds: float = 0.0,
    ) -> None:
        self.model_id = model_id
        self._responses = list(responses or [])
        self._calls = 0
        self._fail_times = fail_times
        self._delay = delay_seconds
        self._lock = threading.Lock()
        self.prompts: list[tuple[str, str]] = []
        self.vision_prompts: list[str] = []

    def complete(
        self,
        *,
        system: str = "",
        user: str = "",
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> ChatResponse:
        if self._delay:
            import time

            time.sleep(self._delay)

        with self._lock:
            self._calls += 1
            call_index = self._calls
            self.prompts.append((system, user))

        if call_index <= self._fail_times:
            raise RuntimeError(f"Fallo simulado del proveedor (llamada {call_index}).")

        if self._responses:
            text = self._responses[(call_index - 1) % len(self._responses)]
        else:
            text = self._synthesize(user)

        return ChatResponse(
            text=text,
            model=self.model_id,
            input_tokens=len(user.split()),
            output_tokens=len(text.split()),
        )

    def describe(
        self,
        *,
        prompt: str,
        image: bytes | None = None,
        pdf: bytes | None = None,
        mime_type: str = "image/png",
        timeout_seconds: float | None = None,
    ) -> ChatResponse:
        with self._lock:
            self.vision_prompts.append(prompt)
        slide_match = re.search(r"diapositiva\s+(\d+)", prompt, re.IGNORECASE)
        number = slide_match.group(1) if slide_match else "1"
        if "FRAGMENTO de HTML" in prompt:
            return ChatResponse(text=_fake_html(number, prompt), model=self.model_id)
        text = (
            f"[Tipo de Diapositiva]\nTexto con un grafico.\n\n"
            f"[Resumen]\nDescripcion simulada de la diapositiva {number}.\n\n"
            f"[Mapa Espacial]\nTitulo arriba, grafico de barras en el centro, "
            f"leyenda a la derecha.\n\n"
            f"[Elementos Visuales Referenciables]\n"
            f"grafico de barras | grafico | centro | evolucion mensual\n"
            f"leyenda | texto | derecha | codigos de color\n\n"
            f"[Lectura Guiada]\n1. Titulo. 2. Grafico. 3. Leyenda."
        )
        return ChatResponse(text=text, model=self.model_id)

    @staticmethod
    def _synthesize(user: str) -> str:
        slide = _SLIDE.search(user)
        expression = _EXPRESSION.search(user)
        number = slide.group(1) if slide else "1"
        surface = expression.group(1).strip() if expression else "la referencia"
        return (
            f"Grafico de barras de la diapositiva {number}: el valor mas alto "
            f"corresponde a marzo, con 42 por ciento."
            if surface
            else f"Elemento principal de la diapositiva {number}."
        )

    @property
    def is_available(self) -> bool:
        return True

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._calls

_INVENTORY_BOX = re.compile(r"^\[Bounding box \d+ \| id=(\S+) \| tipo=(\w+)")
_INVENTORY_TEXT = re.compile(r"^Texto(?:\s*\(fs_max=[\d.]+\))?:\s*(.+)$")

def _fake_html(number: str, prompt: str) -> str:

    bloques: list[tuple[str, str, str]] = []
    identificador = tipo = ""
    for linea in prompt.splitlines():
        caja = _INVENTORY_BOX.match(linea)
        if caja:
            identificador, tipo = caja.group(1), caja.group(2)
            continue
        contenido = _INVENTORY_TEXT.match(linea)
        if contenido and identificador:
            bloques.append((identificador, tipo, contenido.group(1).strip()))
            identificador = ""

    titulo = bloques[0][2] if bloques else f"Diapositiva {number}"
    partes = [
        f'<section aria-labelledby="slide-{number}-titulo">',
        f'<h2 id="slide-{number}-titulo"'
        + (f' data-element-id="{bloques[0][0]}"' if bloques else "")
        + f">{titulo}</h2>",
    ]
    for identificador, _tipo, texto in bloques[1:]:
        partes.append(f'<p data-element-id="{identificador}">{texto}</p>')
    if not bloques:
        partes.append(f"<p>Descripcion simulada de la diapositiva {number}.</p>")
    partes.append("</section>")
    return "".join(partes)

class SlowFakeChatModel(FakeChatModel):

    def __init__(self, *, delay_seconds: float = 5.0, **kwargs) -> None:
        super().__init__(delay_seconds=delay_seconds, **kwargs)

class FailingChatModel:

    name = "failing"
    model_id = "failing-1"

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error or RuntimeError("El proveedor no responde.")

    def complete(self, **_kwargs) -> ChatResponse:
        raise self._error

    def describe(self, **_kwargs) -> ChatResponse:
        raise self._error

    @property
    def is_available(self) -> bool:
        return False
