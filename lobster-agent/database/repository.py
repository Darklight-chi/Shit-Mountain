"""Data access layer."""

from datetime import datetime
from typing import Optional
from database.db import get_session
from database.models import Message, Conversation, Ticket, Order


class MessageRepo:
    def save(self, channel: str, session_id: str, user_id: str,
             role: str, content: str, language: str = "zh",
             message_type: str = "text", raw_payload: dict = None):
        s = get_session()
        try:
            msg = Message(
                channel=channel, session_id=session_id, user_id=user_id,
                role=role, content=content, language=language,
                message_type=message_type, raw_payload=raw_payload,
            )
            s.add(msg)
            s.commit()
            return msg.id
        finally:
            s.close()

    def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        s = get_session()
        try:
            rows = (s.query(Message)
                    .filter(Message.session_id == session_id)
                    .order_by(Message.created_at.desc())
                    .limit(limit).all())
            return [{"role": r.role, "content": r.content} for r in reversed(rows)]
        finally:
            s.close()


class ConversationRepo:
    def get_or_create(self, channel: str, session_id: str, user_id: str) -> dict:
        s = get_session()
        try:
            conv = s.query(Conversation).filter(
                Conversation.session_id == session_id).first()
            if not conv:
                conv = Conversation(
                    channel=channel, session_id=session_id, user_id=user_id)
                s.add(conv)
                s.commit()
            return {"id": conv.id, "status": conv.status,
                    "last_intent": conv.last_intent,
                    "needs_handoff": conv.needs_handoff}
        finally:
            s.close()

    def update(self, session_id: str, **kwargs):
        s = get_session()
        try:
            conv = s.query(Conversation).filter(
                Conversation.session_id == session_id).first()
            if conv:
                for k, v in kwargs.items():
                    setattr(conv, k, v)
                conv.updated_at = datetime.utcnow()
                s.commit()
        finally:
            s.close()


class TicketRepo:
    def create(self, conversation_id: int, reason: str,
               summary: str, priority: str = "medium") -> int:
        s = get_session()
        try:
            t = Ticket(conversation_id=conversation_id, reason=reason,
                       summary=summary, priority=priority)
            s.add(t)
            s.commit()
            return t.id
        finally:
            s.close()


class OrderRepo:
    def get_by_order_id(self, order_id: str) -> Optional[dict]:
        s = get_session()
        try:
            o = s.query(Order).filter(Order.order_id == order_id).first()
            if not o:
                return None
            return {
                "order_id": o.order_id, "user_id": o.user_id,
                "status": o.status, "shipping_status": o.shipping_status,
                "tracking_number": o.tracking_number, "carrier": o.carrier,
                "estimated_delivery": o.estimated_delivery, "address": o.address,
            }
        finally:
            s.close()

    def get_latest_by_user(self, user_id: str) -> Optional[dict]:
        s = get_session()
        try:
            o = (s.query(Order).filter(Order.user_id == user_id)
                 .order_by(Order.created_at.desc()).first())
            if not o:
                return None
            return {
                "order_id": o.order_id, "status": o.status,
                "shipping_status": o.shipping_status,
                "tracking_number": o.tracking_number,
            }
        finally:
            s.close()
