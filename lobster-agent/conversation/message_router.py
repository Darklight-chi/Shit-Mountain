"""Route incoming messages through the full processing pipeline."""

from adapters.base import IncomingMessage
from conversation.session_manager import SessionManager
from conversation.deduplicator import Deduplicator
from loguru import logger


class MessageRouter:
    def __init__(self):
        self.session_mgr = SessionManager()
        self.dedup = Deduplicator()

    def should_process(self, msg: IncomingMessage) -> bool:
        if self.dedup.is_duplicate(msg.channel, msg.session_id, msg.content):
            logger.debug(f"Duplicate message skipped: {msg.content[:30]}")
            return False
        return True

    def prepare_context(self, msg: IncomingMessage) -> dict:
        """Build processing context for the agent."""
        session = self.session_mgr.ensure_session(
            msg.channel, msg.session_id, msg.user_id)
        self.session_mgr.save_message(
            msg.channel, msg.session_id, msg.user_id, "user", msg.content)
        history = self.session_mgr.get_history(msg.session_id)
        return {
            "session": session,
            "history": history,
            "message": msg.content,
            "channel": msg.channel,
            "session_id": msg.session_id,
            "user_id": msg.user_id,
        }

    def save_reply(self, msg: IncomingMessage, reply: str, language: str = "zh"):
        self.session_mgr.save_message(
            msg.channel, msg.session_id, msg.user_id, "assistant", reply, language)
