"""Runner: Xianyu / Ozon live loop and CLI demo."""

import asyncio
import random
from loguru import logger
from adapters.xianyu_adapter import XianyuAdapter
from conversation.message_router import MessageRouter
from agent.graph import run_agent
from config.settings import XIANYU_POLL_INTERVAL


router = MessageRouter()


async def run_xianyu_loop():
    """Live loop: poll Xianyu for messages, process, reply."""
    adapter = XianyuAdapter()
    await adapter.setup()
    logger.info("Xianyu adapter ready. Listening for messages...")

    try:
        while True:
            messages = await adapter.fetch_new_messages()
            for msg in messages:
                if not router.should_process(msg):
                    continue

                logger.info(f"[{msg.channel}] User: {msg.content}")
                context = router.prepare_context(msg)
                context["channel_context"] = await adapter.get_session_context(msg.session_id)
                result = run_agent(context)

                reply = result["reply"]
                locale = result["locale"]

                # Random delay before reply to feel more human
                await asyncio.sleep(random.uniform(1.0, 3.0))

                sent = await adapter.send_reply(msg.session_id, reply)
                if sent:
                    router.save_reply(msg, reply, locale)
                    logger.info(f"[{msg.channel}] Bot: {reply}")
                else:
                    logger.warning(f"[{msg.channel}] Failed to send reply to {msg.session_id}")

                # Update session state
                router.session_mgr.update_session(
                    msg.session_id,
                    last_intent=result["intent"],
                    last_risk_level=result["risk_level"],
                    needs_handoff=result["needs_handoff"],
                )

            # Randomize poll interval slightly to avoid detection
            jitter = random.uniform(-1.0, 2.0)
            await asyncio.sleep(max(2, XIANYU_POLL_INTERVAL + jitter))
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await adapter.teardown()


def run_cli_demo():
    """Interactive CLI for testing the agent without Xianyu."""
    from adapters.base import IncomingMessage

    print("\nLobster Agent CLI Demo")
    print("=" * 40)
    print("Type a message to test. Type 'quit' to exit.\n")

    session_id = "cli_demo_001"
    user_id = "demo_user"

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

        if not router.should_process(msg):
            print("(duplicate, skipped)")
            continue

        context = router.prepare_context(msg)
        result = run_agent(context)

        reply = result["reply"]
        locale = result["locale"]
        intent = result["intent"]
        risk = result["risk_level"]

        router.save_reply(msg, reply, locale)
        router.session_mgr.update_session(
            session_id,
            last_intent=intent,
            last_risk_level=risk,
            needs_handoff=result["needs_handoff"],
        )

        print(f"Lobster [{intent}|{risk}]: {reply}\n")


async def run_ozon_loop():
    """Live loop: poll Ozon Seller API for messages, process, reply."""
    from adapters.ozon_adapter import OzonAdapter

    adapter = OzonAdapter()
    await adapter.setup()
    logger.info("Ozon adapter ready. Listening for messages...")

    ozon_router = MessageRouter()
    poll_interval = 10  # Ozon API rate limits are more lenient

    try:
        while True:
            messages = await adapter.fetch_new_messages()
            for msg in messages:
                if not ozon_router.should_process(msg):
                    continue

                logger.info(f"[{msg.channel}] Buyer: {msg.content}")
                context = ozon_router.prepare_context(msg)
                context["channel_context"] = await adapter.get_session_context(msg.session_id)
                result = run_agent(context)

                reply = result["reply"]
                locale = result["locale"]

                sent = await adapter.send_reply(msg.session_id, reply)
                if sent:
                    ozon_router.save_reply(msg, reply, locale)
                    logger.info(f"[{msg.channel}] Bot: {reply}")

                ozon_router.session_mgr.update_session(
                    msg.session_id,
                    last_intent=result["intent"],
                    last_risk_level=result["risk_level"],
                    needs_handoff=result["needs_handoff"],
                )

            await asyncio.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Shutting down Ozon loop...")
    finally:
        await adapter.teardown()
