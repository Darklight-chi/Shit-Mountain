"""Session lifecycle: create, update, summarize, close."""

from database.repository import ConversationRepo, MessageRepo
from loguru import logger

conv_repo = ConversationRepo()
msg_repo = MessageRepo()


class SessionManager:
    def ensure_session(self, channel: str, session_id: str, user_id: str) -> dict:
        return conv_repo.get_or_create(channel, session_id, user_id)

    def save_message(self, channel: str, session_id: str, user_id: str,
                     role: str, content: str, language: str = "zh"):
        msg_repo.save(channel, session_id, user_id, role, content, language)

    def get_history(self, session_id: str, limit: int = 10) -> list[dict]:
        return msg_repo.get_history(session_id, limit)

    def update_session(self, session_id: str, **kwargs):
        conv_repo.update(session_id, **kwargs)
        logger.debug(f"Session {session_id} updated: {kwargs}")

    def mark_escalated(self, session_id: str):
        conv_repo.update(session_id, status="escalated", needs_handoff=True)
