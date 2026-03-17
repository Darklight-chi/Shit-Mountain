"""Operational flow tests for Xianyu / Ozon."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.graph import run_agent
from conversation.escalation import EscalationManager
from conversation.session_manager import SessionManager
from database.db import init_db


def test_follow_up_greeting_resumes_previous_intent():
    init_db()
    result = run_agent(
        {
            "message": "在吗",
            "history": [
                {"role": "user", "content": "帮我查一下订单"},
                {"role": "assistant", "content": "好的，我帮您看下"},
            ],
            "user_id": "demo_user",
            "channel": "xianyu",
            "session": {"id": 1, "last_intent": "order_status", "needs_handoff": False},
        }
    )
    assert result["intent"] == "order_status"
    assert "A10239" in result["reply"]


def test_repeated_fallback_escalates_on_xianyu():
    init_db()
    result = run_agent(
        {
            "message": "阿巴阿巴这怎么整",
            "history": [
                {"role": "user", "content": "asd"},
                {"role": "assistant", "content": "请再详细说明一下"},
                {"role": "user", "content": "qwe"},
                {"role": "assistant", "content": "我再帮您确认"},
                {"role": "user", "content": "zxc"},
            ],
            "user_id": "demo_user",
            "channel": "xianyu",
            "session": {"id": 2, "last_intent": "fallback", "needs_handoff": False},
        }
    )
    assert result["needs_handoff"] is True
    assert result["risk_level"] == "medium"


def test_shipped_cancellation_escalates_on_ozon():
    init_db()
    result = run_agent(
        {
            "message": "cancel order B20001",
            "history": [],
            "user_id": "en_user",
            "channel": "ozon",
            "session": {"id": 3, "last_intent": "order_status", "needs_handoff": False},
        }
    )
    assert result["intent"] == "cancellation"
    assert result["needs_handoff"] is True


def test_existing_handoff_session_does_not_create_new_flow():
    init_db()
    result = run_agent(
        {
            "message": "还在吗",
            "history": [{"role": "user", "content": "我要投诉"}],
            "user_id": "demo_user",
            "channel": "xianyu",
            "session": {"id": 4, "last_intent": "complaint", "needs_handoff": True},
        }
    )
    assert result["needs_handoff"] is True
    assert "人工" in result["reply"]


def test_handoff_accept_and_resolve_flow():
    init_db()
    session_mgr = SessionManager()
    esc_mgr = EscalationManager()

    session_mgr.ensure_session("xianyu", "handoff-demo", "demo_user")
    session_mgr.mark_escalated("handoff-demo")
    conversation = session_mgr.get_session("handoff-demo")
    ticket_id = esc_mgr.create_ticket(
        conversation_id=conversation["id"],
        reason="manual_review",
        summary="channel=xianyu | latest=需要人工介入",
        priority="high",
    )

    accepted = esc_mgr.accept_ticket("handoff-demo")
    assert accepted is not None
    assert accepted["ticket"]["id"] == ticket_id
    assert accepted["ticket"]["status"] == "in_progress"

    resolved = esc_mgr.resolve_ticket("handoff-demo", "人工已处理完成")
    assert resolved is not None
    assert resolved["ticket"]["status"] == "resolved"
    assert resolved["session"]["status"] == "resolved"
    assert resolved["session"]["needs_handoff"] is False


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
