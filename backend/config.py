"""Settings, paths, and where the API key comes from.

The grader clones the repo into a folder that holds their own .env one level above it:

    submissions/
    ├── .env            <- PORTKEY_API_KEY lives here
    └── rentrail/       <- this repo

So we look for .env in the repo folder first, then in the folder above it. Variables that are
already set in the environment (for example on Render) are never overwritten.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent

ENV_FILES_CHECKED: list[str] = []
for _folder in (REPO_DIR, REPO_DIR.parent):
    _env = _folder / ".env"
    if _env.is_file():
        load_dotenv(_env, override=False)
        ENV_FILES_CHECKED.append(str(_env))

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# Runtime data (database, encrypted uploads, local encryption key). Never committed.
DATA_DIR = Path(os.getenv("RENTRAIL_DATA_DIR") or (REPO_DIR / "instance")).resolve()
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "rentrail.db"
KEY_PATH = DATA_DIR / "secret.key"

SAMPLE_DIR = BACKEND_DIR / "sample_data"
LAW_DIR = BACKEND_DIR / "law"
PROMPTS_DIR = BACKEND_DIR / "prompts"
STATIC_DIR = REPO_DIR / "frontend" / "dist"

# The one model the course key may call.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
REQUEST_TIMEOUT = 90.0  # seconds per model call (vision calls with several frames can be slow)

# Spending guards (tokens = input + output as reported by the gateway).
RUN_TOKEN_LIMIT = 150_000        # one run (e.g. one deposit case) can never use more than this
USER_DAILY_TOKEN_LIMIT = 800_000  # one account per day
RUN_REQUEST_LIMIT = 12            # model requests per agent call

# Upload limits.
MAX_UPLOAD_MB = 80
MAX_VIDEO_SECONDS = 180
MAX_FRAMES_PER_VIDEO = 6   # keyframes sent to the vision model per video
IMAGE_MAX_SIDE = 1024      # images are resized before the model sees them

PORT = int(os.getenv("PORT") or os.getenv("RENTRAIL_PORT") or 8460)
SEED_DEMO = (os.getenv("RENTRAIL_SEED_DEMO") or "1") != "0"


def api_key() -> str | None:
    return os.getenv("PORTKEY_API_KEY")


def key_status() -> dict:
    """What the UI shows about the key, never the key itself."""
    return {
        "portkey_key_found": bool(api_key()),
        "env_files": [Path(p).parent.name + "/.env" for p in ENV_FILES_CHECKED],
        "model": MODEL_NAME,
    }
