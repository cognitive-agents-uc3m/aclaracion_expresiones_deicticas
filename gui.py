import logging
import os
import uvicorn
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.api import build_api
from app.shared import shared_presentation
from app.web_api import build_web_routes, install_fallback_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_AUTO_KEY = "comodin"
_INDEX_PATH = os.path.join(_STATIC_DIR, "index.html")

shared_presentation.set_session_key(_AUTO_KEY)
_auto_sid = install_fallback_session()

api = build_api()
web_router = build_web_routes()
api.include_router(web_router)
api.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@api.get("/")
async def index():
    with open(_INDEX_PATH, "rb") as f:
        content = f.read()
    resp = HTMLResponse(content=content)
    resp.set_cookie("sid", _auto_sid, httponly=True, samesite="lax", path="/")
    resp.set_cookie("role", "teacher", httponly=False, samesite="lax", path="/")
    return resp

if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=7860, log_level="info")