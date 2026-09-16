from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class ShortcutAction(str, Enum):
    LISTEN_CLARIFICATION = "listen_clarification"
    ANNOUNCE_SLIDE = "announce_slide"
    INSERT_CLARIFICATION = "insert_clarification"
    JUMP_TO_SLIDE_NOTES = "jump_to_slide_notes"

    @property
    def description(self) -> str:
        return {
            ShortcutAction.LISTEN_CLARIFICATION: "Escuchar la ultima aclaracion",
            ShortcutAction.ANNOUNCE_SLIDE: "Decir en que diapositiva esta la clase",
            ShortcutAction.INSERT_CLARIFICATION: "Insertar la aclaracion en los apuntes",
            ShortcutAction.JUMP_TO_SLIDE_NOTES: "Ir a los apuntes de la diapositiva actual",
        }[self]

@dataclass(frozen=True, slots=True)
class ShortcutConflict:
    combo: str
    software: str
    detail: str
    suggestion: str

KNOWN_CONFLICTS: tuple[ShortcutConflict, ...] = (
    ShortcutConflict(
        "F2",
        "NVDA",
        "F2 es 'pasar la siguiente tecla a la aplicacion': NVDA la intercepta.",
        "Alt+Shift+N",
    ),
    ShortcutConflict(
        "F1",
        "navegador",
        "F1 abre la ayuda del navegador.",
        "Alt+Shift+H",
    ),
    ShortcutConflict(
        "F3",
        "navegador",
        "F3 abre la busqueda en la pagina.",
        "Alt+Shift+B",
    ),
    ShortcutConflict(
        "F5",
        "navegador",
        "F5 recarga la pagina y se perderia el estado de la clase.",
        "Alt+Shift+R",
    ),
    ShortcutConflict(
        "F6",
        "navegador",
        "F6 mueve el foco entre las zonas del navegador.",
        "Alt+Shift+Z",
    ),
    ShortcutConflict(
        "F7",
        "NVDA/Firefox",
        "F7 activa el cursor de navegacion por teclado en Firefox y se usa en algunos "
        "perfiles de NVDA.",
        "Alt+Shift+E",
    ),
    ShortcutConflict(
        "F11",
        "navegador",
        "F11 alterna la pantalla completa.",
        "Alt+Shift+P",
    ),
    ShortcutConflict(
        "F12",
        "navegador",
        "F12 abre las herramientas de desarrollo.",
        "Alt+Shift+D",
    ),
    ShortcutConflict(
        "Insert",
        "NVDA/JAWS",
        "Insert es la tecla modificadora de NVDA y de JAWS.",
        "Alt+Shift+I",
    ),
    ShortcutConflict(
        "CapsLock",
        "NVDA",
        "CapsLock es la modificadora alternativa de NVDA en portatiles.",
        "Alt+Shift+C",
    ),
)

CONFLICTS_BY_COMBO = {conflict.combo.lower(): conflict for conflict in KNOWN_CONFLICTS}

RECOMMENDED = {
    ShortcutAction.LISTEN_CLARIFICATION: "Alt+Shift+E",
    ShortcutAction.ANNOUNCE_SLIDE: "Alt+Shift+D",
    ShortcutAction.INSERT_CLARIFICATION: "Alt+Shift+A",
    ShortcutAction.JUMP_TO_SLIDE_NOTES: "Alt+Shift+N",
}

@dataclass(frozen=True, slots=True)
class ShortcutBinding:
    action: ShortcutAction
    combo: str
    conflict: ShortcutConflict | None = None

    @property
    def has_conflict(self) -> bool:
        return self.conflict is not None

    @property
    def accessible_label(self) -> str:
        return f"{self.action.description}: {self.combo}"

def resolve(configured: dict[str, str] | None = None) -> list[ShortcutBinding]:

    settings = configured or {}
    bindings: list[ShortcutBinding] = []
    for action in ShortcutAction:
        combo = str(settings.get(action.value) or RECOMMENDED[action]).strip()
        bindings.append(
            ShortcutBinding(
                action=action,
                combo=combo,
                conflict=CONFLICTS_BY_COMBO.get(combo.lower()),
            )
        )
    return bindings

def conflicts(configured: dict[str, str] | None = None) -> list[ShortcutBinding]:
    return [binding for binding in resolve(configured) if binding.has_conflict]

def help_text(configured: dict[str, str] | None = None) -> str:

    lines = ["Atajos de teclado disponibles:"]
    for binding in resolve(configured):
        lines.append(f"{binding.combo}: {binding.action.description}.")
    problems = conflicts(configured)
    if problems:
        lines.append("")
        lines.append("Avisos de compatibilidad:")
        for binding in problems:
            assert binding.conflict is not None
            lines.append(
                f"{binding.combo} puede no funcionar: {binding.conflict.detail} "
                f"Alternativa sugerida: {binding.conflict.suggestion}."
            )
    return "\n".join(lines)

def to_payload(configured: dict[str, str] | None = None) -> dict:

    return {
        "bindings": [
            {
                "action": binding.action.value,
                "combo": binding.combo,
                "description": binding.action.description,
                "conflict": (
                    {
                        "software": binding.conflict.software,
                        "detail": binding.conflict.detail,
                        "suggestion": binding.conflict.suggestion,
                    }
                    if binding.conflict
                    else None
                ),
            }
            for binding in resolve(configured)
        ],
        "help_text": help_text(configured),
    }
