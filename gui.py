from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from cognitive_agent.infrastructure.config.settings import load_settings
from cognitive_agent.infrastructure.logging.setup import configure_logging

def main() -> int:
    import uvicorn

    settings = load_settings()
    configure_logging(level=settings.logging.level, fmt=settings.logging.format)
    uvicorn.run(
        "cognitive_agent.adapters.inbound.http.app:get_asgi_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
