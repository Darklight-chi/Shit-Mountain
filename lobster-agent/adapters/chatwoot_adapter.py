"""Chatwoot adapter — placeholder for future migration."""

from adapters.base import BaseChannelAdapter, IncomingMessage
from loguru import logger


class ChatwootAdapter(BaseChannelAdapter):
    channel_name = "chatwoot"

    async def fetch_new_messages(self) -> list[IncomingMessage]:
        logger.debug("ChatwootAdapter.fetch_new_messages — not implemented yet")
        return []

    async def send_reply(self, session_id: str, text: str) -> bool:
        logger.debug("ChatwootAdapter.send_reply — not implemented yet")
        return False

    async def get_session_context(self, session_id: str) -> dict:
        return {"channel": "chatwoot", "session_id": session_id}
