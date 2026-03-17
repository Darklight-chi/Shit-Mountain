"""Global settings loaded from environment."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# LLM — OpenClaw Gateway (OpenAI-compatible endpoint)
# Set OPENAI_BASE_URL to your OpenClaw gateway, e.g. http://localhost:3000/v1
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:3000/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openclaw:default")
OPENCLAW_AGENT_ID = os.getenv("OPENCLAW_AGENT_ID", "")

# Channel — Xianyu
XIANYU_HEADLESS = os.getenv("XIANYU_HEADLESS", "false").lower() == "true"
XIANYU_POLL_INTERVAL = int(os.getenv("XIANYU_POLL_INTERVAL", "5"))
XIANYU_MAX_REPLY_LENGTH = int(os.getenv("XIANYU_MAX_REPLY_LENGTH", "500"))

# Channel — Ozon (future)
OZON_CLIENT_ID = os.getenv("OZON_CLIENT_ID", "")
OZON_API_KEY = os.getenv("OZON_API_KEY", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'storage' / 'lobster.db'}")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Language
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "zh")

# Knowledge base path
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

# Anti-detection
STEALTH_ENABLED = os.getenv("STEALTH_ENABLED", "true").lower() == "true"
HUMAN_TYPING_DELAY = int(os.getenv("HUMAN_TYPING_DELAY", "80"))  # ms per char
