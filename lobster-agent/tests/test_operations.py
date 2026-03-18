"""Operational flow tests for Xianyu / Ozon."""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.base import IncomingMessage
from agent.graph import run_agent
from app.runner import process_incoming_message
from conversation.message_router import MessageRouter
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


def test_existing_handoff_session_can_resume_tracking_lookup():
    init_db()
    result = run_agent(
        {
            "message": "tracking A10239",
            "history": [
                {"role": "user", "content": "please ship soon"},
                {"role": "assistant", "content": "manual handoff in progress"},
            ],
            "user_id": "demo_user",
            "channel": "xianyu",
            "session": {"id": 5, "last_intent": "shipping_time", "needs_handoff": True},
        }
    )
    assert result["intent"] == "tracking_status"
    assert result["needs_handoff"] is False
    assert "人工" not in result["reply"]
    assert "Carrier:" in result["reply"]
    assert "ETA:" in result["reply"]


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


def test_existing_handoff_session_can_resend_same_reply():
    init_db()
    router = MessageRouter()
    session_mgr = router.session_mgr
    session_id = f"handoff-resend-demo-{uuid.uuid4().hex[:8]}"
    handoff_text = "您的问题已记录，我现在为您转接人工客服，请稍等。"

    session_mgr.ensure_session("xianyu", session_id, "demo_user")
    session_mgr.save_message("xianyu", session_id, "demo_user", "assistant", handoff_text)
    session_mgr.update_session(
        session_id,
        status="escalated",
        last_intent="complaint",
        last_risk_level="high",
        needs_handoff=True,
        summary="channel=xianyu | handoff=yes",
    )

    result = asyncio.run(
        process_incoming_message(
            IncomingMessage(
                channel="xianyu",
                session_id=session_id,
                user_id="demo_user",
                content="还在吗",
            ),
            router=router,
        )
    )

    history = session_mgr.get_history(session_id)
    assistant_replies = [item for item in history if item.get("role") == "assistant"]
    assert result is not None
    assert len(assistant_replies) == 2
    assert assistant_replies[0]["content"] == handoff_text
    assert assistant_replies[-1]["content"] == handoff_text


def test_xianyu_price_question_uses_human_presale_reply():
    init_db()
    result = run_agent(
        {
            "message": "凤阁九霄 这个商品可以价格低一点吗",
            "history": [],
            "user_id": "demo_user",
            "channel": "xianyu",
            "channel_context": {"conversation_title": "凤阁九霄"},
            "session": {"id": 5, "last_intent": "general_greeting", "needs_handoff": False},
        }
    )
    assert result["intent"] == "presale_product"
    assert "知识库" not in result["reply"]
    assert "价格" in result["reply"] or "实在" in result["reply"] or "空间" in result["reply"]


def test_duplicate_outbound_reply_is_saved_to_history():
    init_db()
    router = MessageRouter()
    session_mgr = router.session_mgr
    session_id = f"ozon-dup-guard-{uuid.uuid4().hex[:8]}"

    class FakeAdapter:
        last_send_suppressed = False

        async def get_session_context(self, _session_id: str) -> dict:
            return {"channel": "ozon", "session_id": _session_id}

        async def send_reply(self, _session_id: str, _text: str) -> bool:
            self.last_send_suppressed = True
            return True

    session_mgr.ensure_session("ozon", session_id, "demo_user")

    result = asyncio.run(
        process_incoming_message(
            IncomingMessage(
                channel="ozon",
                session_id=session_id,
                user_id="demo_user",
                content="hello",
            ),
            router=router,
            adapter=FakeAdapter(),
        )
    )

    history = session_mgr.get_history(session_id)
    assistant_replies = [item for item in history if item.get("role") == "assistant"]
    assert result is not None
    assert len(assistant_replies) == 1


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
