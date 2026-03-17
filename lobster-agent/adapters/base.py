"""Base channel adapter — all platforms implement this interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IncomingMessage:
    """Normalized message from any channel."""
    channel: str
    session_id: str
    user_id: str
    content: str
    message_type: str = "text"
    raw_payload: dict = field(default_factory=dict)


class BaseChannelAdapter(ABC):
    """Every channel (Xianyu, Shopify, WhatsApp…) implements this."""

    channel_name: str = "unknown"

    @abstractmethod
    async def fetch_new_messages(self) -> list[IncomingMessage]:
        """Poll or receive new messages from the channel."""
        ...

    @abstractmethod
    async def send_reply(self, session_id: str, text: str) -> bool:
        """Send a reply back through the channel."""
        ...

    @abstractmethod
    async def get_session_context(self, session_id: str) -> dict:
        """Get session metadata (user info, conversation state, etc.)."""
        ...

    async def setup(self):
        """One-time setup (login, open browser, etc.)."""
        pass

    async def teardown(self):
        """Cleanup resources."""
        pass
