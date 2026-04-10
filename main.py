from pathlib import Path
import sys


# Keep the app code in health-intel/ while exposing a clean root entrypoint.
ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "health-intel"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.main import app  # noqa: E402


__all__ = ["app"]
