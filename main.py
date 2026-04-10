from pathlib import Path
import sys

from fastapi import HTTPException
from fastapi.responses import FileResponse


ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "health-intel"
ASSETS_DIR = APP_DIR / "frontend" / "assets"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.main import app  # noqa: E402


@app.get("/api/health", include_in_schema=False)
def api_health():
    return {"status": "ok"}


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend_fallback(requested_path: str):
    requested = (requested_path or "").strip().lstrip("/")
    if not requested or requested.startswith("api/") or requested.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not found")

    path = Path(requested)
    if path.suffix:
        candidate = ASSETS_DIR / path.name
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        raise HTTPException(status_code=404, detail=f"Frontend asset not found: {requested}")

    html_candidate = ASSETS_DIR / f"{path.name}.html"
    if html_candidate.exists() and html_candidate.is_file():
        return FileResponse(str(html_candidate))

    return FileResponse(str(ASSETS_DIR / "pcube.html"))


__all__ = ["app"]
