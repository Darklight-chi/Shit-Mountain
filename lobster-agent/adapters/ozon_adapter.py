"""Ozon marketplace adapter — API-based integration.

Ozon provides a seller API for messaging:
- POST /v1/chat/send  — send message to buyer
- POST /v1/chat/list   — list chats with unread
- POST /v1/chat/history — get chat messages
- POST /v1/chat/read    — mark chat as read

Auth: Client-Id + Api-Key headers

Docs: https://docs.ozon.ru/api/seller/
"""

import time
from typing import Any, Optional

import httpx
from loguru import logger

from adapters.base import BaseChannelAdapter, IncomingMessage
from config.settings import OZON_CLIENT_ID, OZON_API_KEY


OZON_API_BASE = "https://api-seller.ozon.ru"


class OzonAdapter(BaseChannelAdapter):
    """Ozon seller chat adapter using the official Seller API."""

    channel_name = "ozon"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._seen_ids: set[str] = set()
        self._baseline_initialized: bool = False
        self._last_poll: float = 0.0

    async def setup(self):
        if not OZON_CLIENT_ID or not OZON_API_KEY:
            logger.warning(
                "Ozon credentials not configured. "
                "Set OZON_CLIENT_ID and OZON_API_KEY in .env"
            )
            return

        self._client = httpx.AsyncClient(
            base_url=OZON_API_BASE,
            headers={
                "Client-Id": OZON_CLIENT_ID,
                "Api-Key": OZON_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        logger.info("Ozon adapter initialized.")

    async def teardown(self):
        if self._client:
            await self._client.aclose()

    async def fetch_new_messages(self) -> list[IncomingMessage]:
        """Poll Ozon chat API for new buyer messages."""
        if not self._client:
            return []

        messages: list[IncomingMessage] = []
        try:
            # Step 1: Get list of chats with unread messages
            chats = await self._list_unread_chats()

            if not self._baseline_initialized:
                primed = await self._prime_existing_unread_messages(chats)
                self._baseline_initialized = True
                self._last_poll = time.time()
                if primed:
                    logger.info(f"Ozon baseline initialized, skipped {primed} existing unread messages.")
                return []

            for chat in chats:
                chat_id = chat.get("chat_id", "")
                if not chat_id:
                    continue

                # Step 2: Get message history for each unread chat
                history = await self._get_chat_history(chat_id)
                for msg_data in history:
                    msg_id = str(msg_data.get("message_id", ""))
                    if msg_id in self._seen_ids:
                        continue
                    # Only process buyer messages (not our own)
                    if msg_data.get("is_seller", False):
                        self._seen_ids.add(msg_id)
                        continue

                    text = msg_data.get("text", "").strip()
                    if not text:
                        self._seen_ids.add(msg_id)
                        continue

                    self._seen_ids.add(msg_id)
                    messages.append(
                        IncomingMessage(
                            channel=self.channel_name,
                            session_id=chat_id,
                            user_id=chat.get("buyer_id", chat_id),
                            content=text,
                            raw_payload=msg_data,
                        )
                    )

                # Step 3: Mark chat as read
                await self._mark_read(chat_id)

            self._last_poll = time.time()

        except Exception as exc:
            logger.error(f"Error fetching Ozon messages: {exc}")

        return messages

    async def _prime_existing_unread_messages(self, chats: list[dict]) -> int:
        """On first poll, record current unread backlog as seen to avoid replying to stale messages."""
        primed_count = 0
        for chat in chats:
            chat_id = chat.get("chat_id", "")
            if not chat_id:
                continue
            history = await self._get_chat_history(chat_id)
            primed_count += self._mark_history_seen(history)
        return primed_count

    async def send_reply(self, session_id: str, text: str) -> bool:
        """Send a reply to an Ozon buyer chat."""
        if not self._client:
            return False

        try:
            resp = await self._client.post(
                "/v1/chat/send",
                json={"chat_id": session_id, "text": text},
            )
            if resp.status_code == 200:
                logger.info(f"Sent Ozon reply to {session_id}: {text[:60]}")
                return True
            logger.warning(f"Ozon send failed ({resp.status_code}): {resp.text}")
            return False
        except Exception as exc:
            logger.error(f"Ozon send error: {exc}")
            return False

    async def get_session_context(self, session_id: str) -> dict:
        """Get Ozon chat context (product info, order info if available)."""
        context: dict[str, Any] = {
            "channel": self.channel_name,
            "session_id": session_id,
        }

        if not self._client:
            return context

        try:
            # Try to get chat details (may include product/order refs)
            resp = await self._client.post(
                "/v1/chat/history",
                json={"chat_id": session_id, "limit": 1, "offset": 0},
            )
            if resp.status_code == 200:
                data = resp.json()
                chat_info = data.get("chat", {})
                context["product_name"] = chat_info.get("product_name", "")
                context["order_number"] = chat_info.get("order_number", "")
        except Exception:
            pass

        return context

    # -----------------------------------------------------------------------
    # Internal API helpers
    # -----------------------------------------------------------------------

    async def _list_unread_chats(self) -> list[dict]:
        """Get chats with unread messages."""
        if not self._client:
            return []
        try:
            resp = await self._client.post(
                "/v1/chat/list",
                json={"unread_only": True, "limit": 20, "offset": 0},
            )
            if resp.status_code == 200:
                return resp.json().get("chats", [])
            logger.warning(f"Ozon chat list failed ({resp.status_code})")
        except Exception as exc:
            logger.error(f"Ozon chat list error: {exc}")
        return []

    async def _get_chat_history(self, chat_id: str, limit: int = 10) -> list[dict]:
        """Get recent messages for a chat."""
        if not self._client:
            return []
        try:
            resp = await self._client.post(
                "/v1/chat/history",
                json={"chat_id": chat_id, "limit": limit, "offset": 0},
            )
            if resp.status_code == 200:
                return resp.json().get("messages", [])
        except Exception as exc:
            logger.error(f"Ozon history error: {exc}")
        return []

    async def _mark_read(self, chat_id: str):
        """Mark a chat as read."""
        if not self._client:
            return
        try:
            await self._client.post(
                "/v1/chat/read",
                json={"chat_id": chat_id},
            )
        except Exception:
            pass

    def _mark_history_seen(self, history: list[dict]) -> int:
        """Mark a batch of Ozon messages as seen without replying."""
        marked = 0
        for msg_data in history:
            msg_id = str(msg_data.get("message_id", ""))
            if not msg_id or msg_id in self._seen_ids:
                continue
            self._seen_ids.add(msg_id)
            marked += 1
        return marked
