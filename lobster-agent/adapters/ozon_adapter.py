"""Ozon marketplace adapter — API-based integration.

Ozon provides a seller API for messaging:
- POST /v1/chat/send  — send message to buyer
- POST /v1/chat/list   — list chats with unread
- POST /v1/chat/history — get chat messages
- POST /v1/chat/read    — mark chat as read

Auth: Client-Id + Api-Key headers

Docs: https://docs.ozon.ru/api/seller/
"""

import hashlib
import time
from typing import Any, Optional

import httpx
from loguru import logger

from adapters.base import BaseChannelAdapter, IncomingMessage
from config.settings import OZON_CLIENT_ID, OZON_API_KEY


OZON_API_BASE = "https://api-seller.ozon.ru"
BASELINE_GRACE_SECONDS = 8.0


class OzonAdapter(BaseChannelAdapter):
    """Ozon seller chat adapter using the official Seller API."""

    channel_name = "ozon"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._seen_ids: set[str] = set()
        self._recent_replies: dict[str, tuple[str, float]] = {}
        self.last_send_suppressed: bool = False
        self._baseline_initialized: bool = False
        self._startup_at: float = time.time()
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
                if self._should_wait_for_initial_baseline(chats):
                    return []
                primed = await self._prime_existing_unread_messages(chats) if chats else 0
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
                    message_key = self._history_message_key(chat_id, msg_data)
                    if message_key in self._seen_ids:
                        continue
                    # Only process buyer messages (not our own)
                    if msg_data.get("is_seller", False):
                        self._seen_ids.add(message_key)
                        continue

                    text = msg_data.get("text", "").strip()
                    if not text:
                        self._seen_ids.add(message_key)
                        continue

                    self._seen_ids.add(message_key)
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

    def _should_wait_for_initial_baseline(self, chats: list[dict]) -> bool:
        if chats:
            return False
        return (time.time() - self._startup_at) < BASELINE_GRACE_SECONDS

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
            message_key = self._history_message_key("", msg_data)
            if not message_key or message_key in self._seen_ids:
                continue
            self._seen_ids.add(message_key)
            marked += 1
        return marked

    @staticmethod
    def _history_message_key(chat_id: str, msg_data: dict[str, Any]) -> str:
        message_id = str(msg_data.get("message_id", "")).strip()
        if message_id:
            return message_id

        basis = "|".join(
            [
                str(chat_id or msg_data.get("chat_id", "")).strip(),
                str(msg_data.get("created_at", "")).strip(),
                str(msg_data.get("is_seller", False)).strip(),
                str(msg_data.get("text", "")).strip(),
            ]
        )
        if not basis.replace("|", "").strip():
            return ""
        return f"ozon_fallback_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:16]}"

    def _should_suppress_duplicate_reply(self, session_id: str, text: str) -> bool:
        normalized_text = " ".join((text or "").split()).strip()
        if not session_id or not normalized_text:
            return False

        previous = self._recent_replies.get(session_id)
        if not previous:
            return False

        previous_text, sent_at = previous
        return previous_text == normalized_text and (time.time() - sent_at) <= 20

    def _record_recent_reply(self, session_id: str, text: str):
        normalized_text = " ".join((text or "").split()).strip()
        if session_id and normalized_text:
            self._recent_replies[session_id] = (normalized_text, time.time())
