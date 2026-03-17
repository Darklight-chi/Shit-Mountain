"""Xianyu channel adapter backed by Playwright."""

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from playwright.async_api import BrowserContext, Error as PlaywrightError, Locator, Page, async_playwright

from adapters.base import BaseChannelAdapter, IncomingMessage
from config.settings import XIANYU_HEADLESS


SESSION_DIR = Path(__file__).resolve().parent.parent / "storage" / "xianyu_session"

MESSAGE_LIST_SCRIPT = """
() => {
  const textOf = (node) => (node?.innerText || node?.textContent || "").trim();
  const classOf = (node) => (node?.className && typeof node.className === "string") ? node.className : "";
  const dataIdOf = (node) => (
    node?.getAttribute?.("data-id")
    || node?.getAttribute?.("data-mid")
    || node?.getAttribute?.("data-message-id")
    || ""
  );
  const bubbles = Array.from(
    document.querySelectorAll([
      "[data-message-id]",
      "[data-mid]",
      "[class*='message']",
      "[class*='msg']",
      "[class*='bubble']",
      "[class*='chat-item']"
    ].join(","))
  );
  return bubbles
    .map((node, index) => {
      const text = textOf(node);
      if (!text) return null;
      const row = node.closest(
        "[data-message-id], [data-mid], [class*='message'], [class*='msg'], [class*='bubble'], li, [role='listitem']"
      ) || node;
      const rowClass = classOf(row).toLowerCase();
      const bubbleClass = classOf(node).toLowerCase();
      const side = rowClass + " " + bubbleClass;
      const outgoing = /(self|mine|owner|seller|me|right|send|outgoing)/.test(side);
      const incoming = /(other|buyer|customer|left|receive|incoming)/.test(side);
      const authorNode = row.querySelector("[class*='nick'], [class*='name'], [data-role='name']");
      const timeNode = row.querySelector("time, [class*='time']");
      return {
        index,
        text,
        message_id: dataIdOf(row) || dataIdOf(node),
        author: textOf(authorNode),
        timestamp: textOf(timeNode),
        outgoing,
        incoming,
        class_name: classOf(row) || classOf(node),
      };
    })
    .filter(Boolean)
    .slice(-30);
}
"""

CONVERSATION_LIST_SCRIPT = """
() => {
  const textOf = (node) => (node?.innerText || node?.textContent || "").trim();
  const classOf = (node) => (node?.className && typeof node.className === "string") ? node.className : "";
  const candidates = Array.from(
    document.querySelectorAll([
      "[data-session-id]",
      "[data-conversation-id]",
      "[class*='conversation']",
      "[class*='session']",
      "[class*='chat-item']",
      "[role='listitem']"
    ].join(","))
  );
  const seen = new Set();
  return candidates
    .map((node, index) => {
      const sessionId = (
        node.getAttribute("data-session-id")
        || node.getAttribute("data-conversation-id")
        || node.getAttribute("data-id")
        || ""
      ).trim();
      const titleNode = node.querySelector("[class*='title'], [class*='name'], [class*='nick']");
      const previewNode = node.querySelector("[class*='preview'], [class*='snippet'], [class*='last']");
      const badgeNode = node.querySelector("[class*='unread'], [class*='badge'], [aria-label*='未读']");
      const active = /(active|selected|current)/.test(classOf(node).toLowerCase());
      const title = textOf(titleNode) || textOf(node).split("\\n").find(Boolean) || "";
      const preview = textOf(previewNode);
      const key = sessionId || `${title}-${preview}`;
      if (!title || seen.has(key)) return null;
      seen.add(key);
      return {
        index,
        session_id: sessionId,
        title,
        preview,
        unread: !!badgeNode,
        active,
      };
    })
    .filter(Boolean)
    .slice(0, 50);
}
"""

TEXTAREA_SELECTORS = [
    "textarea",
    "[contenteditable='true']",
    "[class*='editor'] [contenteditable='true']",
    "[class*='input'] textarea",
]
SEND_BUTTON_SELECTORS = [
    "[class*='send-btn']",
    "button[class*='send']",
    "[aria-label*='发送']",
    "button:has-text('发送')",
]
LOGIN_READY_SELECTORS = [
    "[data-session-id]",
    "[class*='conversation']",
    "[class*='session']",
    "[role='listitem']",
]


class XianyuAdapter(BaseChannelAdapter):
    """Xianyu web chat adapter using Playwright."""

    channel_name = "xianyu"

    def __init__(self):
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._pw = None
        self._seen_ids: set[str] = set()
        self._conversation_cache: dict[str, dict[str, Any]] = {}

    async def setup(self):
        """Launch browser and load Xianyu. First run needs manual QR login."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=XIANYU_HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self._page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=45000)

        try:
            await self._wait_for_any_selector(LOGIN_READY_SELECTORS, timeout=60000)
            logger.info("Xianyu IM page ready.")
        except Exception:
            logger.warning("Xianyu page did not expose chat list within 60s; manual login may still be required.")

    async def fetch_new_messages(self) -> list[IncomingMessage]:
        """Read unread conversations and return newly received buyer messages."""
        if not self._page:
            return []

        messages: list[IncomingMessage] = []
        try:
            conversations = await self._read_conversation_summaries()
            targets = [conv for conv in conversations if conv.get("unread")] or conversations[:1]

            for summary in targets[:5]:
                if not await self._open_conversation(summary):
                    continue

                await asyncio.sleep(0.6)
                session_id = await self._get_current_session_id(summary)
                summary["session_id"] = session_id
                self._conversation_cache[session_id] = summary

                payloads = await self._read_current_messages()
                for payload in self._select_new_incoming_payloads(session_id, payloads):
                    self._seen_ids.add(self._build_message_key(session_id, payload))
                    messages.append(
                        IncomingMessage(
                            channel=self.channel_name,
                            session_id=session_id,
                            user_id=session_id,
                            content=payload["text"],
                            raw_payload={
                                **payload,
                                "conversation_title": summary.get("title", ""),
                                "conversation_preview": summary.get("preview", ""),
                            },
                        )
                    )
        except Exception as exc:
            logger.error(f"Error fetching Xianyu messages: {exc}")

        return messages

    async def send_reply(self, session_id: str, text: str) -> bool:
        """Send a reply back to the matching Xianyu conversation."""
        if not self._page:
            return False

        try:
            summary = self._conversation_cache.get(session_id)
            if summary:
                if not await self._open_conversation(summary):
                    logger.warning(f"Failed to reopen cached Xianyu conversation: {session_id}")
                    return False
            else:
                conversations = await self._read_conversation_summaries()
                matched = self._match_conversation(session_id, conversations)
                if not matched:
                    logger.warning(f"Unable to locate Xianyu conversation for session: {session_id}")
                    return False
                if not await self._open_conversation(matched):
                    logger.warning(f"Unable to activate Xianyu conversation for session: {session_id}")
                    return False
                self._conversation_cache[session_id] = matched

            input_box = await self._find_input_box()
            if not input_box:
                logger.warning("Xianyu input box not found.")
                return False

            await self._fill_input_box(input_box, text)
            await asyncio.sleep(0.2)

            for selector in SEND_BUTTON_SELECTORS:
                button = self._page.locator(selector).first
                if await button.count():
                    await button.click()
                    self._remember_outgoing(session_id, text)
                    logger.info(f"Sent Xianyu reply to {session_id}: {text[:60]}")
                    return True

            await input_box.press("Enter")
            self._remember_outgoing(session_id, text)
            logger.info(f"Sent Xianyu reply to {session_id}: {text[:60]}")
            return True
        except Exception as exc:
            logger.error(f"Failed to send Xianyu reply: {exc}")
            return False

    async def get_session_context(self, session_id: str) -> dict:
        """Return cached conversation metadata for smarter replies."""
        context = {"channel": self.channel_name, "session_id": session_id}
        cached = self._conversation_cache.get(session_id)
        if cached:
            context.update(
                {
                    "conversation_title": cached.get("title", ""),
                    "conversation_preview": cached.get("preview", ""),
                }
            )
        return context

    async def teardown(self):
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()

    async def _wait_for_any_selector(self, selectors: list[str], timeout: int = 30000):
        if not self._page:
            return
        for selector in selectors:
            try:
                await self._page.wait_for_selector(selector, timeout=timeout)
                return
            except PlaywrightError:
                continue
        raise TimeoutError(f"None of the selectors became available: {selectors}")

    async def _read_conversation_summaries(self) -> list[dict[str, Any]]:
        if not self._page:
            return []
        conversations = await self._page.evaluate(CONVERSATION_LIST_SCRIPT)
        return [conv for conv in conversations if conv.get("title")]

    async def _read_current_messages(self) -> list[dict[str, Any]]:
        if not self._page:
            return []
        return await self._page.evaluate(MESSAGE_LIST_SCRIPT)

    async def _open_conversation(self, summary: dict[str, Any]) -> bool:
        if not self._page:
            return False

        session_id = (summary.get("session_id") or "").strip()
        title = (summary.get("title") or "").strip()
        preview = (summary.get("preview") or "").strip()

        if session_id:
            for selector in (
                f"[data-session-id='{session_id}']",
                f"[data-conversation-id='{session_id}']",
                f"[data-id='{session_id}']",
            ):
                locator = self._page.locator(selector).first
                if await locator.count():
                    await locator.click()
                    return True

        if title:
            title_locator = self._page.get_by_text(title, exact=False).first
            if await title_locator.count():
                await title_locator.click()
                return True

        if preview:
            preview_locator = self._page.get_by_text(preview, exact=False).first
            if await preview_locator.count():
                await preview_locator.click()
                return True

        return False

    async def _get_current_session_id(self, summary: dict[str, Any]) -> str:
        if self._page:
            url = self._page.url
            if "sessionId=" in url:
                return url.split("sessionId=", 1)[1].split("&", 1)[0]

        session_id = (summary.get("session_id") or "").strip()
        if session_id:
            return session_id

        base = f"{summary.get('title', '')}|{summary.get('preview', '')}"
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
        return f"xianyu_{digest}"

    async def _find_input_box(self) -> Optional[Locator]:
        if not self._page:
            return None
        for selector in TEXTAREA_SELECTORS:
            locator = self._page.locator(selector).first
            if await locator.count():
                return locator
        return None

    async def _fill_input_box(self, input_box: Locator, text: str):
        if not self._page:
            return
        editable = await input_box.get_attribute("contenteditable")
        tag_name = await input_box.evaluate("(node) => node.tagName.toLowerCase()")
        await input_box.click()
        if editable == "true" or tag_name != "textarea":
            await input_box.fill("")
            await self._page.keyboard.type(text)
            return
        await input_box.fill(text)

    def _remember_outgoing(self, session_id: str, text: str):
        payload = {"text": text, "message_id": f"outgoing-{len(self._seen_ids)}"}
        self._seen_ids.add(self._build_message_key(session_id, payload))

    def _match_conversation(self, session_id: str, conversations: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        for summary in conversations:
            if summary.get("session_id") == session_id:
                return summary
        cached = self._conversation_cache.get(session_id)
        if not cached:
            return None
        for summary in conversations:
            if summary.get("title") == cached.get("title"):
                return summary
        return None

    def _select_new_incoming_payloads(
        self, session_id: str, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        for payload in reversed(payloads):
            if payload.get("outgoing"):
                continue
            message_key = self._build_message_key(session_id, payload)
            if message_key in self._seen_ids:
                return []
            return [payload]
        return []

    @staticmethod
    def _build_message_key(session_id: str, payload: dict[str, Any]) -> str:
        message_id = (payload.get("message_id") or "").strip()
        text = (payload.get("text") or "").strip()
        timestamp = (payload.get("timestamp") or "").strip()
        author = (payload.get("author") or "").strip()
        basis = message_id or f"{author}|{timestamp}|{text}"
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()
        return f"{session_id}:{digest}"
