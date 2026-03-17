"""Lobster Agent — main entry point."""

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from config.settings import LOG_LEVEL
from database.db import init_db
from app.runner import run_xianyu_loop, run_cli_demo


def setup_logging():
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL, format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add("storage/lobster.log", rotation="10 MB", level="DEBUG")


def main():
    setup_logging()
    init_db()
    logger.info("Lobster Agent initialized.")

    mode = sys.argv[1] if len(sys.argv) > 1 else "cli"

    if mode == "xianyu":
        logger.info("Starting Xianyu live mode...")
        asyncio.run(run_xianyu_loop())
    elif mode == "cli":
        logger.info("Starting CLI demo mode...")
        run_cli_demo()
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python -m app.main [cli|xianyu]")


if __name__ == "__main__":
    main()
