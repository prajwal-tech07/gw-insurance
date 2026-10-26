"""Settings, read from environment variables (and an optional backend/.env file)."""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
DATA_DIR = APP_DIR / "data"
SAMPLES_DIR = BACKEND_DIR / "samples"
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from backend/.env without overriding real env vars."""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def db_path() -> Path:
    return Path(os.environ.get("CLAIMSAATHI_DB", str(BACKEND_DIR / "claimsaathi.db")))


def claude_model() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")


def llm_enabled() -> bool:
    """The AI reader is optional: on only when a key is configured and not disabled."""
    if os.environ.get("CLAIMSAATHI_DISABLE_LLM") == "1":
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
