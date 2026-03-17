"""Xianyu (闲鱼) channel adapter via Playwright."""

import asyncio
import json
from pathlib import Path
from typing import Optional
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page
from adapters.base import BaseChannelAdapter, IncomingMessage
from config.settings import XIANYU_HEADLESS, XIANYU_POLL_INTERVAL


SESSION_DIR = Path(__file__).resolve().parent.parent / "storage" / "xianyu_session"


class XianyuAdapter(BaseChannelAdapter):
    """Xianyu web chat adapter using Playwright."""

    channel_name = "xianyu"

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._pw = None
        self._seen_ids: set[str] = set()

    async def setup(self):
        """Launch browser and load Xianyu. First run needs manual QR login."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=XIANYU_HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()

        # Navigate to Xianyu message page
        await self._page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=30000)
        logger.info("Xianyu IM page loaded. If first run, please scan QR code to login.")

        # Wait for login — check for chat list presence
        try:
            await self._page.wait_for_selector('[class*="conversation"]', timeout=60000)
            logger.info("Xianyu login confirmed — chat list visible.")
        except Exception:
            logger.warning("Chat list not found in 60s. May need manual login.")

    async def fetch_new_messages(self) -> list[IncomingMessage]:
        """Scrape new unread messages from the active conversations."""
        messages = []
        if not self._page:
            return messages

        try:
            # Find unread conversation badges
            unread_items = await self._page.query_selector_all('[class*="unread"], [class*="badge"]')
            for item in unread_items[:5]:  # Process up to 5 unread conversations
                await item.click()
                await asyncio.sleep(1)

                # Extract messages from the chat panel
                msg_elements = await self._page.query_selector_all('[class*="message-content"], [class*="msg-text"]')
                session_id = await self._get_current_session_id()

                for el in msg_elements[-3:]:  # Last 3 messages
                    text = await el.inner_text()
                    msg_id = f"{session_id}_{hash(text)}"
                    if msg_id not in self._seen_ids and text.strip():
                        self._seen_ids.add(msg_id)
                        messages.append(IncomingMessage(
                            channel="xianyu",
                            session_id=session_id,
                            user_id=session_id,
                            content=text.strip(),
                        ))
        except Exception as e:
            logger.error(f"Error fetching Xianyu messages: {e}")

        return messages

    async def send_reply(self, session_id: str, text: str) -> bool:
        """Type and send a reply in the current chat."""
        if not self._page:
            return False
        try:
            # Find the input box
            input_box = await self._page.query_selector(
                '[class*="chat-input"] textarea, [class*="editor"] textarea, textarea'
            )
            if input_box:
                await input_box.fill(text)
                await asyncio.sleep(0.3)
                # Press Enter or click send button
                send_btn = await self._page.query_selector('[class*="send-btn"], button[class*="send"]')
                if send_btn:
                    await send_btn.click()
                else:
                    await input_box.press("Enter")
                logger.info(f"Sent reply to {session_id}: {text[:50]}...")
                return True
            else:
                logger.warning("Input box not found on Xianyu.")
                return False
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            return False

    async def get_session_context(self, session_id: str) -> dict:
        return {"channel": "xianyu", "session_id": session_id}

    async def _get_current_session_id(self) -> str:
        """Extract current conversation session ID from URL or DOM."""
        try:
            url = self._page.url
            if "sessionId=" in url:
                return url.split("sessionId=")[1].split("&")[0]
        except Exception:
            pass
        return f"xianyu_{id(self._page)}"

    async def teardown(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
