"""Tests for the Ozon adapter helpers."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.ozon_adapter import OzonAdapter


def test_mark_history_seen_primes_existing_backlog():
    adapter = OzonAdapter()
    history = [
        {"message_id": "oz-old-1", "text": "old one"},
        {"message_id": "oz-old-2", "text": "old two"},
    ]
    assert adapter._mark_history_seen(history) == 2
    assert adapter._mark_history_seen(history) == 0


def test_mark_history_seen_allows_future_new_message():
    adapter = OzonAdapter()
    adapter._mark_history_seen([{"message_id": "oz-old-1", "text": "old one"}])

    incoming = {"message_id": "oz-new-1", "text": "new one"}
    assert adapter._mark_history_seen([incoming]) == 1
    assert "oz-new-1" in adapter._seen_ids


def test_history_message_key_falls_back_without_message_id():
    key1 = OzonAdapter._history_message_key(
        "chat-1",
        {
            "created_at": "2026-03-17T23:00:00Z",
            "is_seller": False,
            "text": "hello",
        },
    )
    key2 = OzonAdapter._history_message_key(
        "chat-1",
        {
            "created_at": "2026-03-17T23:00:00Z",
            "is_seller": False,
            "text": "hello",
        },
    )
    assert key1 == key2
    assert key1.startswith("ozon_fallback_")


def test_mark_history_seen_uses_fallback_key_when_message_id_missing():
    adapter = OzonAdapter()
    history = [
        {
            "chat_id": "chat-1",
            "created_at": "2026-03-17T23:00:00Z",
            "is_seller": False,
            "text": "hello",
        }
    ]
    assert adapter._mark_history_seen(history) == 1
    assert adapter._mark_history_seen(history) == 0


def test_duplicate_reply_guard_suppresses_same_text_for_same_chat():
    adapter = OzonAdapter()
    adapter._record_recent_reply("chat-1", "Thanks for reaching out")
    assert adapter._should_suppress_duplicate_reply("chat-1", "Thanks for reaching out") is True
    assert adapter._should_suppress_duplicate_reply("chat-1", "Different reply") is False


def test_initial_baseline_waits_briefly_when_no_chats():
    adapter = OzonAdapter()
    adapter._startup_at = time.time()
    assert adapter._should_wait_for_initial_baseline([]) is True


def test_initial_baseline_finishes_after_grace_window():
    adapter = OzonAdapter()
    adapter._startup_at = time.time() - 30
    assert adapter._should_wait_for_initial_baseline([]) is False
    assert adapter._should_wait_for_initial_baseline([{"chat_id": "chat-1"}]) is False


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
