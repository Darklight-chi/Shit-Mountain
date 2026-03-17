"""Tests for the Ozon adapter helpers."""

import sys
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


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
