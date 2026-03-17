"""Reusable JSONL-backed channel adapter for local integration testing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from adapters.base import BaseChannelAdapter, IncomingMessage


class JsonlChannelAdapter(BaseChannelAdapter):
    """Bridge adapter that reads inbound messages from a JSONL file and writes replies to another."""

    def __init__(self, inbox_path: str | Path, outbox_path: str | Path, channel_name: str):
        self.channel_name = channel_name
        self._inbox_path = Path(inbox_path)
        self._outbox_path = Path(outbox_path)
        self._seen_ids: set[str] = set()
        self._cursor = 0
        self._session_context: dict[str, dict[str, Any]] = {}

    async def setup(self):
        self._inbox_path.parent.mkdir(parents=True, exist_ok=True)
        self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
        self._inbox_path.touch(exist_ok=True)
        self._outbox_path.touch(exist_ok=True)

    async def fetch_new_messages(self) -> list[IncomingMessage]:
        entries = self._read_entries()
        if self._cursor > len(entries):
            self._cursor = 0

        messages: list[IncomingMessage] = []
        for entry in entries[self._cursor:]:
            msg = self._build_message(entry)
            if not msg:
                continue
            message_id = self._message_id(msg)
            if message_id in self._seen_ids:
                continue
            self._seen_ids.add(message_id)
            self._session_context[msg.session_id] = {
                "channel": self.channel_name,
                "session_id": msg.session_id,
                "customer_name": entry.get("customer_name", ""),
                "customer_email": entry.get("customer_email", ""),
                "order_id": entry.get("order_id", ""),
                "tags": entry.get("tags", []),
                "source": entry.get("source", self.channel_name),
                "last_payload": entry,
            }
            messages.append(msg)

        self._cursor = len(entries)
        return messages

    async def send_reply(self, session_id: str, text: str) -> bool:
        payload = {
            "session_id": session_id,
            "text": text,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "channel": self.channel_name,
        }
        try:
            with self._outbox_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            logger.info(f"[{self.channel_name}] wrote reply to outbox for {session_id}")
            return True
        except Exception as exc:
            logger.error(f"[{self.channel_name}] failed writing outbox reply: {exc}")
            return False

    async def get_session_context(self, session_id: str) -> dict:
        return self._session_context.get(
            session_id,
            {"channel": self.channel_name, "session_id": session_id},
        )

    def _read_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        try:
            with self._inbox_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning(f"[{self.channel_name}] skip invalid jsonl line: {exc}")
                        continue
                    if isinstance(payload, dict):
                        entries.append(payload)
        except FileNotFoundError:
            return []
        return entries

    def _build_message(self, payload: dict[str, Any]) -> Optional[IncomingMessage]:
        content = str(payload.get("content", "")).strip()
        session_id = str(payload.get("session_id", "")).strip()
        if not content or not session_id:
            return None

        user_id = str(payload.get("user_id") or payload.get("customer_email") or session_id).strip()
        return IncomingMessage(
            channel=self.channel_name,
            session_id=session_id,
            user_id=user_id,
            content=content,
            message_type=str(payload.get("message_type", "text")),
            raw_payload=payload,
        )

    @staticmethod
    def _message_id(msg: IncomingMessage) -> str:
        payload_message_id = str(msg.raw_payload.get("message_id", "")).strip()
        if payload_message_id:
            return payload_message_id
        digest = hashlib.sha1(
            f"{msg.channel}|{msg.session_id}|{msg.user_id}|{msg.content}".encode("utf-8")
        ).hexdigest()
        return digest
