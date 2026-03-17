"""Tests for the Xianyu adapter helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from adapters.xianyu_adapter import XianyuAdapter
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from agent.response_generator import _format_channel_context


def test_build_message_key_prefers_message_id():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    payload = {
        "message_id": "msg-001",
        "author": "buyer",
        "timestamp": "10:00",
        "text": "还在吗",
    }
    key1 = XianyuAdapter._build_message_key("session-a", payload)
    key2 = XianyuAdapter._build_message_key("session-a", {**payload, "text": "另一条文本"})
    assert key1 == key2


def test_select_new_incoming_payloads_returns_new_messages():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    payloads = [
        {"message_id": "old-1", "text": "第一条", "outgoing": False},
        {"message_id": "self-1", "text": "好的", "outgoing": True},
        {"message_id": "new-1", "text": "现在可以发货吗", "outgoing": False},
    ]
    selected = adapter._select_new_incoming_payloads("session-a", payloads)
    ids = [item["message_id"] for item in selected]
    assert "new-1" in ids


def test_select_new_incoming_payloads_skips_seen_message():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    payload = {"message_id": "new-1", "text": "现在可以发货吗", "outgoing": False}
    adapter._seen_ids.add(XianyuAdapter._build_message_key("session-a", payload))
    assert adapter._select_new_incoming_payloads("session-a", [payload]) == []


def test_match_conversation_falls_back_to_cached_title():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    adapter._conversation_cache["session-a"] = {"title": "张三", "preview": "在吗"}
    matched = adapter._match_conversation(
        "session-a",
        [{"session_id": "", "title": "张三", "preview": "新的消息"}],
    )
    assert matched["title"] == "张三"


def test_format_channel_context_basic():
    text = _format_channel_context(
        {
            "conversation_title": "iPhone 15 Pro Max",
            "conversation_preview": "还能便宜吗",
            "session_id": "session-a",
            "channel": "xianyu",
        }
    )
    assert "conversation_title=iPhone 15 Pro Max" in text
    assert "channel=xianyu" in text


def test_format_channel_context_with_order_cards():
    text = _format_channel_context(
        {
            "channel": "xianyu",
            "order_cards": [
                {"title": "AirPods Pro 2", "price": "899", "status": "已付款"},
            ],
        }
    )
    assert "AirPods Pro 2" in text
    assert "899" in text


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                if "SKIP" not in str(func):
                    print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
