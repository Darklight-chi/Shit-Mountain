"""Runner: shared live-loop orchestration and CLI demo."""

import asyncio
import random
import time
from dataclasses import dataclass, field

from loguru import logger

from adapters.base import BaseChannelAdapter, IncomingMessage
from adapters.chatwoot_adapter import ChatwootAdapter
from adapters.ozon_adapter import OzonAdapter
from adapters.shopify_adapter import ShopifyChatAdapter
from adapters.xianyu_adapter import XianyuAdapter
from agent.graph import run_agent
from config.settings import (
    CHATWOOT_POLL_INTERVAL,
    OZON_POLL_INTERVAL,
    SHOPIFY_POLL_INTERVAL,
    XIANYU_POLL_INTERVAL,
)
from conversation.message_router import MessageRouter


MAX_POLL_BACKOFF_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 60


@dataclass
class LoopRuntimeStats:
    mode: str
    started_at: float = field(default_factory=time.time)
    polls: int = 0
    messages_in: int = 0
    replies_sent: int = 0
    handoffs: int = 0
    duplicates: int = 0
    send_failures: int = 0
    process_failures: int = 0
    poll_failures: int = 0
    last_heartbeat_at: float = 0.0

    def heartbeat_due(self) -> bool:
        return time.time() - self.last_heartbeat_at >= HEARTBEAT_INTERVAL_SECONDS

    def log_heartbeat(self):
        uptime = int(time.time() - self.started_at)
        logger.info(
            f"[{self.mode}] heartbeat | uptime={uptime}s polls={self.polls} "
            f"messages_in={self.messages_in} replies_sent={self.replies_sent} "
            f"handoffs={self.handoffs} duplicates={self.duplicates} "
            f"send_failures={self.send_failures} process_failures={self.process_failures} "
            f"poll_failures={self.poll_failures}"
        )
        self.last_heartbeat_at = time.time()


MODE_CONFIG: dict[str, dict] = {
    "xianyu": {
        "factory": XianyuAdapter,
        "poll_interval": XIANYU_POLL_INTERVAL,
        "reply_delay": None,
    },
    "ozon": {
        "factory": OzonAdapter,
        "poll_interval": OZON_POLL_INTERVAL,
        "reply_delay": None,
    },
    "shopify": {
        "factory": ShopifyChatAdapter,
        "poll_interval": SHOPIFY_POLL_INTERVAL,
        "reply_delay": None,
    },
    "chatwoot": {
        "factory": ChatwootAdapter,
        "poll_interval": CHATWOOT_POLL_INTERVAL,
        "reply_delay": None,
    },
}


async def process_incoming_message(
    msg: IncomingMessage,
    router: MessageRouter,
    adapter: BaseChannelAdapter | None = None,
    reply_delay: tuple[float, float] | None = None,
    stats: LoopRuntimeStats | None = None,
) -> dict | None:
    """Run the full pipeline for a single inbound message."""
    if not router.should_process(msg):
        if stats:
            stats.duplicates += 1
        return None

    logger.info(f"[{msg.channel}] User: {msg.content}")
    context = router.prepare_context(msg)
    if adapter:
        context["channel_context"] = await adapter.get_session_context(msg.session_id)

    result = run_agent(context)
    reply = result["reply"]
    locale = result["locale"]
    status = "escalated" if result["needs_handoff"] else "active"

    if adapter:
        if reply_delay:
            await asyncio.sleep(random.uniform(*reply_delay))
        sent = await adapter.send_reply(msg.session_id, reply)
        if not sent:
            if stats:
                stats.send_failures += 1
            logger.warning(f"[{msg.channel}] Failed to send reply to {msg.session_id}")
            return None

    router.save_reply(msg, reply, locale)
    router.session_mgr.update_session(
        msg.session_id,
        status=status,
        last_intent=result["intent"],
        last_risk_level=result["risk_level"],
        needs_handoff=result["needs_handoff"],
        summary=result.get("summary"),
    )
    logger.info(f"[{msg.channel}] Bot: {reply}")

    if stats:
        stats.replies_sent += 1
        if result["needs_handoff"]:
            stats.handoffs += 1
    return result


async def run_live_loop(mode: str):
    """Unified live loop for all channel adapters."""
    config = MODE_CONFIG[mode]
    adapter: BaseChannelAdapter = config["factory"]()
    router = MessageRouter()
    poll_interval = config["poll_interval"]
    reply_delay = config["reply_delay"]
    stats = LoopRuntimeStats(mode=mode)
    consecutive_poll_failures = 0

    await adapter.setup()
    logger.info(f"{mode} adapter ready. Listening for messages...")

    try:
        while True:
            try:
                stats.polls += 1
                messages = await adapter.fetch_new_messages()
                consecutive_poll_failures = 0
            except Exception as exc:
                stats.poll_failures += 1
                consecutive_poll_failures += 1
                backoff_seconds = min(
                    poll_interval * max(2, consecutive_poll_failures),
                    MAX_POLL_BACKOFF_SECONDS,
                )
                logger.exception(
                    f"[{mode}] poll failed #{consecutive_poll_failures}, "
                    f"retrying in {backoff_seconds}s: {exc}"
                )
                await asyncio.sleep(backoff_seconds)
                continue

            stats.messages_in += len(messages)
            for msg in messages:
                try:
                    await process_incoming_message(
                        msg,
                        router=router,
                        adapter=adapter,
                        reply_delay=reply_delay,
                        stats=stats,
                    )
                except Exception as exc:
                    stats.process_failures += 1
                    logger.exception(f"[{mode}] failed processing message {msg.session_id}: {exc}")

            if stats.heartbeat_due():
                stats.log_heartbeat()

            sleep_for = poll_interval
            if mode == "xianyu":
                sleep_for = max(1, poll_interval + random.uniform(0.0, 0.2))
            await asyncio.sleep(sleep_for)
    except KeyboardInterrupt:
        logger.info(f"Shutting down {mode} loop...")
    finally:
        await adapter.teardown()


async def run_xianyu_loop():
    await run_live_loop("xianyu")


async def run_ozon_loop():
    await run_live_loop("ozon")


async def run_shopify_loop():
    await run_live_loop("shopify")


async def run_chatwoot_loop():
    await run_live_loop("chatwoot")


def run_cli_demo():
    """Interactive CLI for testing the agent without a live adapter."""
    print("\nLobster Agent CLI Demo")
    print("=" * 40)
    print("Type a message to test. Type 'quit' to exit.\n")

    session_id = "cli_demo_001"
    user_id = "demo_user"
    router = MessageRouter()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            print("\nBye!")
            break

        msg = IncomingMessage(
            channel="cli",
            session_id=session_id,
            user_id=user_id,
            content=user_input,
        )

        result = asyncio.run(process_incoming_message(msg, router=router))
        if not result:
            print("(duplicate, skipped)")
            continue

        print(f"Lobster [{result['intent']}|{result['risk_level']}]: {result['reply']}\n")
