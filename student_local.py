import logging
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from student.ui import build_demo

demo = build_demo()

if __name__ == "__main__":
    import torch
    logging.getLogger(__name__).info(
        "Torch version=%s cuda=%s available=%s",
        torch.__version__, torch.version.cuda, torch.cuda.is_available(),
    )
    try:
        result = subprocess.run(
            ["ollama", "ps"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout or "").strip()
        if output:
            logging.getLogger(__name__).info("[Ollama]\n%s", output)
    except Exception as ex:
        logging.getLogger(__name__).warning("No se pudo comprobar estado GPU: %s: %s", type(ex).__name__, ex)

    demo.launch(server_name="0.0.0.0", server_port=7861)