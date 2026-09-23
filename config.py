from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("STUDY_DB_PATH", BASE_DIR / "study.db"))
AI_PROVIDER = os.getenv("AI_PROVIDER", "offline").lower()
AI_MODEL = os.getenv("MODEL_NAME", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MAX_DOCUMENT_TEXT = 2_000_000


def ai_enabled() -> bool:
    return bool(OPENROUTER_API_KEY and AI_PROVIDER not in {"", "offline"})
