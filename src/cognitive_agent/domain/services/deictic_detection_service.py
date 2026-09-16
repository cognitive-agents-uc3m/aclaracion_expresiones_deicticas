from __future__ import annotations

import re
from dataclasses import dataclass

from ..value_objects.deictic import DeicticDetection, DeicticExpression, DeicticKind
from ..value_objects.transcript import fold_accents

_FLAGS = re.IGNORECASE

@dataclass(frozen=True, slots=True)
class DeicticRule:
    name: str
    kind: DeicticKind
    pattern: re.Pattern[str]
    confidence: float

@dataclass(frozen=True, slots=True)
class SuppressionRule:
    name: str
    pattern: re.Pattern[str]
    reason: str

def _rule(name: str, kind: DeicticKind, expr: str, confidence: float) -> DeicticRule:
    return DeicticRule(name, kind, re.compile(expr, _FLAGS), confidence)

_VISUAL_NOUNS = (
    r"grafic[ao]s?|tablas?|figuras?|imagen(?:es)?|diagramas?|formulas?|ecuaciones?|"
    r"clases?|flechas?|cajas?|columnas?|filas?|celdas?|lineas?|curvas?|barras?|"
    r"ejes?|eje|nodos?|bloques?|requisitos?|opciones?|opcion|casillas?|recuadros?|"
    r"esquemas?|mapas?|leyendas?|titulos?|apartados?|puntos?|valores?|valor|"
    r"histogramas?|sectores?|cuadros?|matrices?|matriz|actores?|componentes?|"
    r"relaciones?|relacion|asociaciones?|asociacion|multiplicidades?|casos? de uso"
)

DEFAULT_RULES: tuple[DeicticRule, ...] = (

    _rule(
        "demostrativo_mas_objeto_visual",
        DeicticKind.VISUAL_OBJECT,
        rf"\b(?:est[aeo]s?|es[ao]s?|aquel(?:la|los|las)?)\s+(?:{_VISUAL_NOUNS})\b",
        0.95,
    ),
    _rule(
        "articulo_mas_objeto_visual_senalado",
        DeicticKind.VISUAL_OBJECT,
        rf"\b(?:l[ao]s?|el)\s+(?:{_VISUAL_NOUNS})\s+(?:de\s+(?:aqui|ahi|arriba|abajo|la\s+derecha|la\s+izquierda))\b",
        0.9,
    ),
    _rule(
        "donde_apunta",
        DeicticKind.VISUAL_OBJECT,
        r"\bdonde\s+(?:apunta|senala|esta)\s+(?:la|el)\s+\w+",
        0.85,
    ),

    _rule("lugar_aqui", DeicticKind.PLACE, r"\baqui\b", 0.9),
    _rule("lugar_ahi", DeicticKind.PLACE, r"\bahi\b", 0.9),
    _rule("lugar_alli", DeicticKind.PLACE, r"\balli\b", 0.8),
    _rule("lugar_aca", DeicticKind.PLACE, r"\bac[a]\b", 0.75),

    _rule(
        "espacial_direccion",
        DeicticKind.SPATIAL,
        r"\b(?:a\s+la\s+)?(?:derecha|izquierda)\b|\bparte\s+(?:superior|inferior|de\s+arriba|de\s+abajo)\b"
        r"|\ben\s+(?:la\s+esquina|el\s+centro|el\s+medio)\b|\barriba\b|\babajo\b"
        r"|\b(?:justo\s+)?(?:debajo|encima)\b|\bal\s+lado\b",
        0.75,
    ),

    _rule(
        "percepcion_imperativa",
        DeicticKind.PERCEPTION,
        r"\b(?:fijaos|fijense|fijate|mirad|miren|mira|observad|observen|observa)\b",
        0.85,
    ),
    _rule(
        "percepcion_colectiva",
        DeicticKind.PERCEPTION,
        r"\bcomo\s+(?:veis|ven|podeis\s+ver|pueden\s+ver|se\s+ve|se\s+aprecia)\b"
        r"|\bse\s+puede\s+ver\b|\bos\s+ense[nñ]o\b|\baqui\s+teneis\b",
        0.85,
    ),
    _rule("percepcion_vemos", DeicticKind.PERCEPTION, r"\b(?:vemos|veis|ven)\b", 0.6),

    _rule("demostrativo_neutro", DeicticKind.DEMONSTRATIVE, r"\b(?:esto|eso|aquello)\b", 0.8),
    _rule(
        "demostrativo_concordado",
        DeicticKind.DEMONSTRATIVE,
        r"\b(?:est[ae]|est[ao]s|es[ae]|es[ao]s|aquel(?:la|los|las)?)\b",
        0.6,
    ),
    _rule("asi_modal", DeicticKind.DEMONSTRATIVE, r"\bse\s+hace\s+asi\b|\btiene\s+esta\s+forma\b", 0.8),
)

DEFAULT_SUPPRESSORS: tuple[SuppressionRule, ...] = (
    SuppressionRule(
        "anafora",
        re.compile(
            r"\b(?:esto|eso|est[ae]|es[ae]|aquello)\b[^.;]{0,40}?\b(?:"
            r"que\s+(?:ya\s+)?(?:hemos\s+|habiamos\s+)?(?:visto|vimos|explique|expliqu[eé]|"
            r"explicamos|comente|coment[eé]|dije|dijimos|mencione|mencion[eé]|"
            r"contamos|conte)"
            r"|de\s+antes|anterior(?:mente)?|del\s+(?:tema|capitulo|apartado)\s+anterior"
            r"|de\s+la\s+(?:clase|sesion)\s+(?:pasada|anterior)"
            r")\b",
            _FLAGS,
        ),
        reason="anafora: el referente ya se menciono verbalmente",
    ),
    SuppressionRule(
        "inferencia",
        re.compile(
            r"\b(?:vemos|veis|ven|observamos|se\s+ve|se\s+observa|se\s+deduce|se\s+concluye)\s+que\b",
            _FLAGS,
        ),
        reason="inferencia: 'vemos que' significa 'se deduce', no senala nada",
    ),
    SuppressionRule(
        "lugar_no_pantalla",
        re.compile(
            r"\baqui\s+en\s+(?!la\s+(?:pantalla|diapositiva|imagen|figura|tabla|grafica|"
            r"transparencia|presentacion|pizarra|parte|zona|esquina|columna|fila))",
            _FLAGS,
        ),
        reason="el lugar referido no es la pantalla",
    ),
    SuppressionRule(
        "gestion_de_aula",
        re.compile(
            r"\b(?:examen|practica|entrega|matricula|tutoria|aula\s+\d|horario|"
            r"asistencia|grupo\s+\d)\b.{0,30}\b(?:aqui|esto|esta)\b"
            r"|\b(?:aqui|esto|esta)\b.{0,30}\b(?:examen|practica|entrega|tutoria|horario)\b",
            _FLAGS,
        ),
        reason="gestion de aula: no hay referente visual en la diapositiva",
    ),
)

class DeicticDetectionService:

    def __init__(
        self,
        *,
        rules: tuple[DeicticRule, ...] = DEFAULT_RULES,
        suppressors: tuple[SuppressionRule, ...] = DEFAULT_SUPPRESSORS,
        min_confidence: float = 0.5,
    ) -> None:
        self._rules = rules
        self._suppressors = suppressors
        self._min_confidence = min_confidence

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    def detect(self, text: str) -> DeicticDetection:
        raw = (text or "").strip()
        if not raw:
            return DeicticDetection.none("fragmento vacio")

        folded = fold_accents(raw)

        for suppressor in self._suppressors:
            if suppressor.pattern.search(folded):
                return DeicticDetection.none(suppressor.reason)

        found: list[DeicticExpression] = []
        consumed: list[tuple[int, int]] = []

        for rule in self._rules:
            for match in rule.pattern.finditer(folded):
                start, end = match.span()
                if any(start < c_end and c_start < end for c_start, c_end in consumed):
                    continue
                confidence = rule.confidence
                if confidence < self._min_confidence:
                    continue
                consumed.append((start, end))

                found.append(
                    DeicticExpression(
                        surface=raw[start:end],
                        kind=rule.kind,
                        start=start,
                        end=end,
                        confidence=confidence,
                    )
                )

        if not found:
            return DeicticDetection.none("sin expresiones deicticas")

        found.sort(key=lambda e: e.start)
        return DeicticDetection(expressions=tuple(found), detector="rules")
