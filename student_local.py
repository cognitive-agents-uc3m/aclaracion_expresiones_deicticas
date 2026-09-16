from __future__ import annotations

import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from cognitive_agent.adapters.inbound.gradio import (
    build_student_app,
    launch_student_app,
)
from cognitive_agent.application.dto import StartSessionCommand
from cognitive_agent.domain.value_objects.identifiers import SessionId
from cognitive_agent.domain.value_objects.subject import Subject
from cognitive_agent.infrastructure.config.settings import load_settings
from cognitive_agent.infrastructure.dependency_injection import build_container
from cognitive_agent.infrastructure.logging.setup import configure_logging

def _cuando(sesion) -> str:

    return sesion.started_at.strftime("%d/%m %H:%M") if sesion.started_at else "     ?    "

def _describir(sesion) -> str:
    return f"{sesion.title or '(sin titulo)'} [{sesion.session_id.value[:8]}, {_cuando(sesion)}]"

def elegir_sesion(container):

    activas = sorted(container.sessions.list_active(), key=lambda s: s.started_at)
    return activas[-1] if activas else None

def _listar(container) -> int:

    sesiones = sorted(
        container.sessions.list_active(), key=lambda s: s.started_at, reverse=True
    )
    if not sesiones:
        print("No hay ninguna sesion activa.")
        print("Arranca la plataforma del profesor (python gui.py) y sube un PDF.")
        return 1
    print(f"{'IDENTIFICADOR':34} {'INICIO':>11} {'DIAPOS.':>8}  TITULO")
    for sesion in sesiones:
        marca = " " if sesion.has_deck else "!"
        print(
            f"{marca}{sesion.session_id.value:33} {_cuando(sesion):>11} "
            f"{sesion.slide_count:>8}  {sesion.title or '(sin titulo)'}"
        )
    if any(not s.has_deck for s in sesiones):
        print("\n  ! = sin presentacion cargada: no habra etiquetas ni aclaraciones.")
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Interfaz del alumno.",
        epilog=(
            "Sin --session-id se une automaticamente a la clase activa mas reciente, "
            "tenga presentacion cargada o no. Si no hay ninguna, no arranca: hay que "
            "abrir antes la del profesor, o pedir una suelta con --new. Con --list se "
            "ven todas."
        ),
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Sesion concreta a la que unirse. Por defecto, la ultima que este activa.",
    )
    parser.add_argument("--subject", default=None, help="Asignatura si se crea sesion nueva.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--list", action="store_true", help="Lista las sesiones disponibles y termina."
    )
    parser.add_argument(
        "--new", action="store_true", help="Fuerza crear una sesion nueva y vacia."
    )
    parser.add_argument(
        "--share-lan",
        action="store_true",
        help="Escucha en todas las interfaces. Solo en red de confianza.",
    )
    parser.add_argument(
        "--follow-latest",
        action="store_true",
        help="Cambia automaticamente a la sesion activa mas reciente.",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(level=settings.logging.level, fmt=settings.logging.format)
    container = build_container(settings)

    if args.list:
        codigo = _listar(container)
        container.shutdown()
        return codigo

    if args.session_id:
        session_id = SessionId(args.session_id)
        container.sessions.require(session_id)
    elif not args.new:

        elegida = elegir_sesion(container)
        if elegida is not None:
            session_id = elegida.session_id
            print(f"Unido a la clase: {_describir(elegida)}")
            con_pdf = sorted(
                (s for s in container.sessions.list_active() if s.has_deck),
                key=lambda s: s.started_at,
            )
            if not elegida.has_deck and con_pdf:
                print(
                    "  Aun no tiene presentacion. Si no es la clase que buscabas, la "
                    "ultima con PDF es:"
                )
                print(f"      python student_local.py --session-id {con_pdf[-1].session_id.value}")
        else:

            print("No hay ninguna clase activa a la que unirse.")
            print()
            print("  Arranca primero la plataforma del profesor:")
            print("      python gui.py")
            print("  pulsa 'Iniciar sesion', sube el PDF, y vuelve a lanzar esto.")
            print()
            print("  Para trabajar en una sesion suelta, sin profesor:")
            print("      python student_local.py --new")
            container.shutdown()
            return 1
    else:
        view = container.start_session.execute(
            StartSessionCommand(
                subject=Subject.parse(args.subject or settings.session.default_subject.value),
                title="Sesion de alumno",
            )
        )
        session_id = SessionId(view.session_id)
        print(f"Sesion creada: {session_id.value}")

    sesion = container.sessions.require(session_id)
    if sesion.deck is None:
        print()
        print("  AVISO: esta sesion no tiene presentacion cargada.")
        print("  Sin ella NO apareceran las etiquetas [Diapositiva N] en tus")
        print("  apuntes ni se generaran aclaraciones.")
        print()
        print("  Arranca antes la plataforma del profesor (python gui.py), sube")
        print("  el PDF y vuelve a lanzar esto: se unira solo a esa clase.")
        print()
        print("  Para ver las sesiones disponibles:")
        print("      python student_local.py --list")
        print()
        print(f"  Ambos procesos deben usar el mismo entorno (ahora: {settings.environment})")
        print("  y persistencia en disco. Con COGNITIVE_AGENT_ENV=test cada proceso")
        print("  guarda en memoria y no se ven entre si.")
        print()
    else:
        print(
            f"Presentacion: {sesion.deck.title or sesion.deck.deck_id.value[:12]} "
            f"({sesion.slide_count} diapositivas)"
        )

    demo = build_student_app(container, session_id, follow_latest=args.follow_latest)
    try:

        launch_student_app(
            demo,
            server_name="0.0.0.0" if args.share_lan else args.host,
            server_port=args.port or settings.server.student_ui_port,
        )
    finally:
        container.shutdown()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
