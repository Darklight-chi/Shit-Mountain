"""Global settings loaded from environment."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "qwen2.5:7b")

# Channel
XIANYU_HEADLESS = os.getenv("XIANYU_HEADLESS", "false").lower() == "true"
XIANYU_POLL_INTERVAL = int(os.getenv("XIANYU_POLL_INTERVAL", "5"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'storage' / 'lobster.db'}")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Language
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "zh")

# Knowledge base path
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
