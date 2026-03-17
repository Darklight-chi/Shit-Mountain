"""Lobster Agent main entry point."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from app.handoff_cli import run_handoff_cli
from app.runner import (
    run_chatwoot_loop,
    run_cli_demo,
    run_ozon_loop,
    run_shopify_loop,
    run_xianyu_loop,
)
from config.settings import LOG_LEVEL
from database.db import init_db


LIVE_MODE_RUNNERS = {
    "xianyu": run_xianyu_loop,
    "ozon": run_ozon_loop,
    "shopify": run_shopify_loop,
    "chatwoot": run_chatwoot_loop,
}


def setup_logging():
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL, format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add("storage/lobster.log", rotation="10 MB", level="DEBUG")


def main():
    setup_logging()
    init_db()
    logger.info("Lobster Agent initialized.")

    mode = sys.argv[1] if len(sys.argv) > 1 else "cli"

    if mode == "handoff":
        run_handoff_cli(sys.argv[2:])
        return

    if mode == "cli":
        logger.info("Starting CLI demo mode...")
        run_cli_demo()
        return

    if mode in LIVE_MODE_RUNNERS:
        logger.info(f"Starting {mode} live mode...")
        asyncio.run(LIVE_MODE_RUNNERS[mode]())
        return

    print(f"Unknown mode: {mode}")
    print("Usage: python -m app.main [cli|xianyu|ozon|shopify|chatwoot|handoff]")


if __name__ == "__main__":
    main()
