---
name: clarification
version: v2
role: user
placeholders: [DEICTIC_EXPRESSION, VISUAL_FOCUS, POINTED_ELEMENT, SPEAKER_UTTERANCE, SLIDE_DESCRIPTION, RECENT_CONTEXT, SLIDE_NUMBER, SLIDE_COUNT]
migrated_from: prompts/base/clarification.user.v1.md
notes: >-
  Mismas secciones y mismo contenido que v1. Lo unico que cambia es que el
  elemento apuntado sube al principio -detras de la diapositiva- y se rotula
  como dato prioritario, en coherencia con la regla nueva del prompt de
  sistema. El orden importa: enterrado entre el foco visual y la frase del
  orador, el modelo lo trataba como una pista mas.
---
Diapositiva actual:
{SLIDE_NUMBER} de {SLIDE_COUNT}

>>> ELEMENTO APUNTADO POR EL PROFESOR (dato prioritario) <<<
{POINTED_ELEMENT}

Expresion deictica detectada:
{DEICTIC_EXPRESSION}

Foco visual detectado:
{VISUAL_FOCUS}

Frase del orador:
{SPEAKER_UTTERANCE}

Contexto reciente de la explicacion:
{RECENT_CONTEXT}

Descripcion accesible de la diapositiva:
{SLIDE_DESCRIPTION}
