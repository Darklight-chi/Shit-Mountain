"""Tests for JSONL-backed bridge adapters."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.chatwoot_adapter import ChatwootAdapter
from adapters.shopify_adapter import ShopifyChatAdapter


def _write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_shopify_bridge_adapter_reads_and_writes():
    base_dir = Path(__file__).resolve().parent.parent / "storage" / "test_shopify_bridge"
    inbox = base_dir / "inbox.jsonl"
    outbox = base_dir / "outbox.jsonl"
    _write_jsonl(
        inbox,
        [
            {
                "message_id": "shopify-1",
                "session_id": "conv-1",
                "user_id": "buyer@example.com",
                "customer_email": "buyer@example.com",
                "customer_name": "Buyer",
                "content": "Where is my order B20001?",
                "order_id": "B20001",
            }
        ],
    )

    adapter = ShopifyChatAdapter()
    adapter._inbox_path = inbox
    adapter._outbox_path = outbox
    asyncio.run(adapter.setup())

    messages = asyncio.run(adapter.fetch_new_messages())
    assert len(messages) == 1
    assert messages[0].session_id == "conv-1"

    context = asyncio.run(adapter.get_session_context("conv-1"))
    assert context["order_id"] == "B20001"

    sent = asyncio.run(adapter.send_reply("conv-1", "I checked it for you."))
    assert sent is True
    assert "I checked it for you." in outbox.read_text(encoding="utf-8")


def test_chatwoot_bridge_adapter_deduplicates_by_message_id():
    base_dir = Path(__file__).resolve().parent.parent / "storage" / "test_chatwoot_bridge"
    inbox = base_dir / "inbox.jsonl"
    outbox = base_dir / "outbox.jsonl"
    _write_jsonl(
        inbox,
        [
            {
                "message_id": "cw-1",
                "session_id": "chat-1",
                "user_id": "buyer-1",
                "content": "你好，还在吗",
            }
        ],
    )

    adapter = ChatwootAdapter()
    adapter._inbox_path = inbox
    adapter._outbox_path = outbox
    asyncio.run(adapter.setup())

    first_batch = asyncio.run(adapter.fetch_new_messages())
    second_batch = asyncio.run(adapter.fetch_new_messages())
    assert len(first_batch) == 1
    assert second_batch == []


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
