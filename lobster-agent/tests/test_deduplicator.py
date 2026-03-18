"""Tests for message deduplication behavior."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversation.deduplicator import Deduplicator


def test_deduplicator_uses_message_id_when_available():
    dedup = Deduplicator()
    assert dedup.is_duplicate("xianyu", "session-a", "你好", message_id="msg-1") is False
    assert dedup.is_duplicate("xianyu", "session-a", "你好", message_id="msg-2") is False


def test_deduplicator_falls_back_to_author_timestamp_and_content():
    dedup = Deduplicator()
    assert dedup.is_duplicate("xianyu", "session-a", "你好", timestamp="21:35", author="buyer") is False
    assert dedup.is_duplicate("xianyu", "session-a", "你好", timestamp="21:36", author="buyer") is False
    assert dedup.is_duplicate("xianyu", "session-a", "你好", timestamp="21:36", author="buyer") is True


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
