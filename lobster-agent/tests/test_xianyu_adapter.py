"""Tests for the Xianyu adapter helpers."""

import sys
import time
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
    adapter._seen_ids.add(f"{XianyuAdapter._build_message_key('session-a', payload)}:0")
    assert adapter._select_new_incoming_payloads("session-a", [payload]) == []


def test_mark_payloads_seen_primes_existing_backlog():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    old_payloads = [
        {"message_id": "old-1", "text": "老消息1", "outgoing": False},
        {"message_id": "old-2", "text": "老消息2", "outgoing": False},
    ]
    assert adapter._mark_payloads_seen("session-a", old_payloads) == 2

    later_payloads = old_payloads + [
        {"message_id": "new-1", "text": "新消息", "outgoing": False},
    ]
    selected = adapter._select_new_incoming_payloads("session-a", later_payloads)
    assert [item["message_id"] for item in selected] == ["new-1"]


def test_select_new_incoming_payloads_keeps_repeated_same_text():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    first_payloads = [{"text": "你好", "author": "buyer", "timestamp": "", "outgoing": False}]
    assert adapter._mark_payloads_seen("session-a", first_payloads) == 1

    later_payloads = [
        {"text": "你好", "author": "buyer", "timestamp": "", "outgoing": False},
        {"text": "你好", "author": "buyer", "timestamp": "", "outgoing": False},
    ]
    selected = adapter._select_new_incoming_payloads("session-a", later_payloads)
    assert len(selected) == 1
    assert selected[0]["text"] == "你好"


def test_collapse_dom_duplicate_payloads_keeps_distinct_rows():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    payloads = [
        {"text": "浣犲ソ", "outgoing": False, "top": 120},
        {"text": "浣犲ソ", "outgoing": False, "top": 126},
        {"text": "浣犲ソ", "outgoing": False, "top": 180},
    ]
    collapsed = XianyuAdapter._collapse_dom_duplicate_payloads(payloads)
    assert len(collapsed) == 2
    assert [item["top"] for item in collapsed] == [120, 180]


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


def test_canonical_session_id_stays_stable_when_preview_changes():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    summary_a = {"session_id": "", "title": "凤阁九霄", "preview": "这个商品可以价格低一点吗"}
    summary_b = {"session_id": "", "title": "凤阁九霄", "preview": "真的不能再降一降价格吗"}
    session_a = adapter._canonicalize_session_id("", summary_a)
    session_b = adapter._canonicalize_session_id("", summary_b)
    assert session_a == session_b


def test_duplicate_reply_guard_uses_conversation_title_identity():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    session_id = "xianyu_demo"
    adapter._conversation_cache[session_id] = {"title": "凤阁九霄", "preview": "你好"}
    adapter._record_recent_reply(session_id, "亲，这边已经是比较实在的价格啦")
    assert adapter._should_suppress_duplicate_reply(
        session_id, "亲，这边已经是比较实在的价格啦"
    ) is True
    assert adapter._should_suppress_duplicate_reply(
        session_id, "亲，这边库存还有，您看下~"
    ) is False


def test_initial_baseline_waits_briefly_when_no_targets():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    adapter._startup_at = time.time()
    assert adapter._should_wait_for_initial_baseline([]) is True


def test_initial_baseline_finishes_after_grace_window():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    adapter._startup_at = time.time() - 30
    assert adapter._should_wait_for_initial_baseline([]) is False
    assert adapter._should_wait_for_initial_baseline([{"title": "寮犱笁"}]) is False


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


def test_platform_noise_detection():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    assert XianyuAdapter._is_platform_noise({"text": "你有一条未读消息\n这些宝贝正在热卖，你有吗？\n去发布"}) is True
    assert XianyuAdapter._is_platform_noise({"text": "还在吗"}) is False


def test_match_conversation_ignores_missing_summary():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    matched = adapter._match_conversation(
        "session-a",
        [{"session_id": "", "title": "消息", "preview": ""}],
    )
    assert matched is None


def test_non_human_conversation_detection():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    assert XianyuAdapter._is_non_human_conversation(
        {"title": "无忧工作室", "preview": "期待你的评价"}
    ) is True
    assert XianyuAdapter._is_non_human_conversation(
        {"title": "张三", "preview": "你好"}
    ) is False


def test_non_human_message_detection():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    assert XianyuAdapter._is_non_human_message(
        {"author": "无忧工作室", "text": "你已确认收货，交易成功"}
    ) is True
    assert XianyuAdapter._is_non_human_message(
        {"author": "普通买家", "text": "你好，还在吗"}
    ) is False


def test_select_poll_targets_includes_active_conversation():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    adapter = XianyuAdapter()
    targets = adapter._select_poll_targets(
        [
            {"session_id": "a", "title": "张三", "preview": "你好", "unread": False, "active": True},
            {"session_id": "b", "title": "李四", "preview": "在吗", "unread": True, "active": False},
        ]
    )
    assert [item["session_id"] for item in targets] == ["b", "a"]


def test_non_human_message_detection_for_promotions():
    if not HAS_PLAYWRIGHT:
        print("  SKIP (playwright not installed)")
        return
    assert XianyuAdapter._is_non_human_message(
        {"author": "平台通知", "text": "你的2025闲鱼年度账单请查收，立刻查看"}
    ) is True
    assert XianyuAdapter._is_platform_noise(
        {"text": "优惠券即将过期提醒\n全国特惠电影可用\n去使用"}
    ) is True


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
