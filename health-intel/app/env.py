from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_app_env() -> None:
    """
    Load the project's environment files regardless of the current working
    directory so backend services can resolve API keys reliably.
    """
    project_root = Path(__file__).resolve().parent.parent
    requested_env = os.getenv("APP_ENV", "").strip().lower()
    env_files = []

    if requested_env == "production":
        if (project_root / ".env.production").exists():
            env_files.append(project_root / ".env.production")
        if (project_root / ".env").exists():
            env_files.append(project_root / ".env")
    else:
        if (project_root / ".env").exists():
            env_files.append(project_root / ".env")

    for env_file in env_files:
        load_dotenv(env_file, override=False)
