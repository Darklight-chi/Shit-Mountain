"""Xianyu channel adapter — production-grade Playwright implementation.

Features:
- Stealth anti-detection (webdriver flag, navigator overrides, WebGL noise)
- Persistent login via session directory + automatic re-login detection
- Multi-layer CSS selector fallback for resilience against DOM changes
- Captcha / verification popup detection
- Page crash recovery with automatic reload
- Human-like typing delay
- Rate limiting to avoid triggering anti-bot
"""

import asyncio
import hashlib
import random
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    async_playwright,
)

from adapters.base import BaseChannelAdapter, IncomingMessage
from config.settings import (
    XIANYU_HEADLESS,
    XIANYU_MAX_REPLY_LENGTH,
    STEALTH_ENABLED,
    HUMAN_TYPING_DELAY,
)


SESSION_DIR = Path(__file__).resolve().parent.parent / "storage" / "xianyu_session"

# ---------------------------------------------------------------------------
# Stealth injection script — runs before any page JS
# ---------------------------------------------------------------------------
STEALTH_SCRIPT = """
() => {
  // Hide webdriver flag
  Object.defineProperty(navigator, 'webdriver', { get: () => false });

  // Fake plugins array (real Chrome has plugins)
  Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
  });

  // Fake languages
  Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en-US', 'en'],
  });

  // Override permissions query
  const originalQuery = window.navigator.permissions.query;
  window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters);

  // Fake chrome runtime
  window.chrome = { runtime: {} };

  // Add noise to WebGL fingerprint
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
  };

  // Override canvas fingerprint with subtle noise
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    if (type === 'image/png' && this.width > 16 && this.height > 16) {
      const ctx = this.getContext('2d');
      if (ctx) {
        const style = ctx.fillStyle;
        ctx.fillStyle = 'rgba(0,0,1,0.003)';
        ctx.fillRect(0, 0, 1, 1);
        ctx.fillStyle = style;
      }
    }
    return toDataURL.apply(this, arguments);
  };
}
"""

# ---------------------------------------------------------------------------
# JS: read messages from the active chat panel
# ---------------------------------------------------------------------------
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

  // Multi-strategy: try several selectors for message bubbles
  const selectors = [
    "[data-message-id]",
    "[data-mid]",
    "[class*='MessageItem']",
    "[class*='messageItem']",
    "[class*='message-item']",
    "[class*='msg-item']",
    "[class*='message']",
    "[class*='msg']",
    "[class*='bubble']",
    "[class*='chat-item']",
  ];
  const bubbles = Array.from(document.querySelectorAll(selectors.join(",")));

  return bubbles
    .map((node, index) => {
      const text = textOf(node);
      if (!text || text.length > 2000) return null;

      const row = node.closest(
        "[data-message-id], [data-mid], [class*='message'], [class*='msg'], [class*='bubble'], li, [role='listitem']"
      ) || node;
      const rowClass = classOf(row).toLowerCase();
      const bubbleClass = classOf(node).toLowerCase();
      const side = rowClass + " " + bubbleClass;

      const outgoing = /(self|mine|owner|seller|me|right|send|outgoing)/.test(side);
      const incoming = /(other|buyer|customer|left|receive|incoming)/.test(side);

      const authorNode = row.querySelector("[class*='nick'], [class*='name'], [data-role='name']");
      const timeNode = row.querySelector("time, [class*='time'], [class*='Time']");

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

# ---------------------------------------------------------------------------
# JS: read conversation list sidebar
# ---------------------------------------------------------------------------
CONVERSATION_LIST_SCRIPT = """
() => {
  const textOf = (node) => (node?.innerText || node?.textContent || "").trim();
  const classOf = (node) => (node?.className && typeof node.className === "string") ? node.className : "";

  const selectors = [
    "[data-session-id]",
    "[data-conversation-id]",
    "[class*='SessionItem']",
    "[class*='sessionItem']",
    "[class*='session-item']",
    "[class*='conversation']",
    "[class*='session']",
    "[class*='chat-item']",
    "[role='listitem']",
  ];
  const candidates = Array.from(document.querySelectorAll(selectors.join(",")));
  const seen = new Set();

  return candidates
    .map((node, index) => {
      const sessionId = (
        node.getAttribute("data-session-id")
        || node.getAttribute("data-conversation-id")
        || node.getAttribute("data-id")
        || ""
      ).trim();

      const titleNode = node.querySelector("[class*='title'], [class*='name'], [class*='nick'], [class*='Title'], [class*='Name']");
      const previewNode = node.querySelector("[class*='preview'], [class*='snippet'], [class*='last'], [class*='Preview'], [class*='Snippet']");
      const badgeNode = node.querySelector("[class*='unread'], [class*='badge'], [class*='Unread'], [aria-label*='unread'], [aria-label*='未读']");
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

# ---------------------------------------------------------------------------
# JS: detect login / captcha / error states
# ---------------------------------------------------------------------------
PAGE_STATE_SCRIPT = """
() => {
  const body = document.body?.innerText || "";
  const url = location.href;
  return {
    url,
    hasLoginForm: !!document.querySelector("[class*='login'], [class*='Login'], #login, [id*='login']"),
    hasQRCode: !!document.querySelector("[class*='qrcode'], [class*='QRCode'], [class*='qr-code'], img[src*='qrcode']"),
    hasCaptcha: !!document.querySelector("[class*='captcha'], [class*='Captcha'], [class*='verify'], [class*='Verify'], [class*='slider'], [class*='Slider']"),
    hasError: /(系统繁忙|网络错误|页面不存在|服务器错误|error|50[0-9])/.test(body),
    hasConversationList: !!document.querySelector("[data-session-id], [class*='conversation'], [class*='session'], [class*='SessionItem']"),
    hasChatPanel: !!document.querySelector("textarea, [contenteditable='true']"),
    title: document.title,
  };
}
"""

# ---------------------------------------------------------------------------
# JS: scrape order info from the chat panel (product card / order card)
# ---------------------------------------------------------------------------
ORDER_SCRAPE_SCRIPT = """
() => {
  const textOf = (n) => (n?.innerText || n?.textContent || "").trim();

  // Look for product/order cards in the chat area
  const cardSelectors = [
    "[class*='order-card']", "[class*='OrderCard']",
    "[class*='product-card']", "[class*='ProductCard']",
    "[class*='goods-card']", "[class*='GoodsCard']",
    "[class*='trade-card']", "[class*='TradeCard']",
    "[class*='item-card']", "[class*='ItemCard']",
  ];
  const cards = Array.from(document.querySelectorAll(cardSelectors.join(",")));

  const pricePattern = /[\\u00a5\\uffe5]\\s*([\\d,.]+)/;
  const statusKeywords = ["已付款", "待发货", "已发货", "已完成", "已取消", "交易成功", "退款"];

  const results = [];
  for (const card of cards.slice(-5)) {
    const text = textOf(card);
    const titleEl = card.querySelector("[class*='title'], [class*='name'], [class*='Title'], [class*='Name']");
    const priceEl = card.querySelector("[class*='price'], [class*='Price']");
    const statusEl = card.querySelector("[class*='status'], [class*='Status']");
    const imgEl = card.querySelector("img");

    const priceMatch = (textOf(priceEl) || text).match(pricePattern);
    const detectedStatus = statusKeywords.find(kw => text.includes(kw)) || textOf(statusEl);

    results.push({
      title: textOf(titleEl) || text.split("\\n")[0]?.substring(0, 80) || "",
      price: priceMatch ? priceMatch[1] : "",
      status: detectedStatus,
      image: imgEl?.src || "",
      raw_text: text.substring(0, 300),
    });
  }
  return results;
}
"""

# ---------------------------------------------------------------------------
# Selector sets with fallbacks
# ---------------------------------------------------------------------------
TEXTAREA_SELECTORS = [
    "textarea",
    "[contenteditable='true']",
    "[class*='editor'] [contenteditable='true']",
    "[class*='Editor'] [contenteditable='true']",
    "[class*='input'] textarea",
    "[class*='Input'] textarea",
    "[class*='chat-input'] textarea",
    "[class*='ChatInput'] textarea",
]

SEND_BUTTON_SELECTORS = [
    "[class*='send-btn']",
    "[class*='SendBtn']",
    "[class*='sendBtn']",
    "button[class*='send']",
    "button[class*='Send']",
    "[aria-label*='发送']",
    "[aria-label*='Send']",
    "button:has-text('发送')",
    "button:has-text('Send')",
]

LOGIN_READY_SELECTORS = [
    "[data-session-id]",
    "[class*='SessionItem']",
    "[class*='conversation']",
    "[class*='session']",
    "[role='listitem']",
]


class XianyuAdapter(BaseChannelAdapter):
    """Production-grade Xianyu web chat adapter using Playwright."""

    channel_name = "xianyu"

    def __init__(self):
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._pw = None
        self._seen_ids: set[str] = set()
        self._baseline_initialized: bool = False
        self._conversation_cache: dict[str, dict[str, Any]] = {}
        self._last_activity: float = 0.0
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 5

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    async def setup(self):
        """Launch browser and load Xianyu. First run needs manual QR login."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
        ]

        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=XIANYU_HEADLESS,
            args=launch_args,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )

        # Inject stealth script before page load
        if STEALTH_ENABLED:
            await self._context.add_init_script(STEALTH_SCRIPT)

        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )

        await self._navigate_to_im()
        self._last_activity = time.time()

    async def _navigate_to_im(self):
        """Navigate to Xianyu IM page and wait for readiness."""
        try:
            await self._page.goto(
                "https://www.goofish.com/im",
                wait_until="domcontentloaded",
                timeout=45000,
            )
        except PlaywrightError as exc:
            logger.warning(f"Navigation to IM page had an issue: {exc}")

        # Wait for the chat list to appear (indicates logged-in state)
        try:
            await self._wait_for_any_selector(LOGIN_READY_SELECTORS, timeout=60000)
            logger.info("Xianyu IM page ready — logged in.")
        except TimeoutError:
            state = await self._detect_page_state()
            if state.get("hasQRCode") or state.get("hasLoginForm"):
                logger.warning(
                    "QR code / login form detected. Please scan QR code in the browser window. "
                    "Waiting up to 120s..."
                )
                try:
                    await self._wait_for_any_selector(LOGIN_READY_SELECTORS, timeout=120000)
                    logger.info("Login successful — IM page ready.")
                except TimeoutError:
                    logger.error("Login timeout. Please restart and scan QR code manually.")
            else:
                logger.warning(
                    "IM page did not load within 60s. Will retry on next poll cycle."
                )

    async def teardown(self):
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()

    # -----------------------------------------------------------------------
    # Core: fetch messages
    # -----------------------------------------------------------------------

    async def fetch_new_messages(self) -> list[IncomingMessage]:
        """Read unread conversations and return newly received buyer messages."""
        if not self._page:
            return []

        # Health check before polling
        if not await self._ensure_healthy():
            return []

        messages: list[IncomingMessage] = []
        try:
            conversations = await self._read_conversation_summaries()
            targets = [c for c in conversations if c.get("unread")] or conversations[:1]

            if not self._baseline_initialized:
                primed = await self._prime_existing_unread_messages(targets[:5])
                self._baseline_initialized = True
                self._consecutive_errors = 0
                self._last_activity = time.time()
                if primed:
                    logger.info(f"Xianyu baseline initialized, skipped {primed} existing unread messages.")
                return []

            for summary in targets[:5]:
                if not await self._open_conversation(summary):
                    continue

                await self._human_delay(0.4, 0.8)
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
            self._consecutive_errors = 0
            self._last_activity = time.time()

        except Exception as exc:
            self._consecutive_errors += 1
            logger.error(f"Error fetching messages (#{self._consecutive_errors}): {exc}")
            if self._consecutive_errors >= self._max_consecutive_errors:
                logger.warning("Too many consecutive errors — attempting recovery...")
                await self._recover()

        return messages

    async def _prime_existing_unread_messages(self, targets: list[dict[str, Any]]) -> int:
        """On first poll, record current unread backlog as seen to avoid replying to stale messages."""
        primed_count = 0
        for summary in targets:
            if not await self._open_conversation(summary):
                continue

            await self._human_delay(0.2, 0.4)
            session_id = await self._get_current_session_id(summary)
            summary["session_id"] = session_id
            self._conversation_cache[session_id] = summary
            payloads = await self._read_current_messages()
            primed_count += self._mark_payloads_seen(session_id, payloads)
        return primed_count

    # -----------------------------------------------------------------------
    # Core: send reply
    # -----------------------------------------------------------------------

    async def send_reply(self, session_id: str, text: str) -> bool:
        """Send a reply back to the matching Xianyu conversation."""
        if not self._page:
            return False

        # Truncate overly long replies
        if len(text) > XIANYU_MAX_REPLY_LENGTH:
            text = text[:XIANYU_MAX_REPLY_LENGTH - 3] + "..."

        try:
            # Locate the right conversation
            if not await self._activate_conversation(session_id):
                return False

            input_box = await self._find_input_box()
            if not input_box:
                logger.warning("Input box not found.")
                return False

            await self._fill_input_box_human(input_box, text)
            await self._human_delay(0.15, 0.35)

            # Try send button, then Enter key
            sent = False
            for selector in SEND_BUTTON_SELECTORS:
                button = self._page.locator(selector).first
                if await button.count():
                    await button.click()
                    sent = True
                    break

            if not sent:
                await input_box.press("Enter")

            self._remember_outgoing(session_id, text)
            logger.info(f"Sent reply to {session_id}: {text[:60]}")
            self._last_activity = time.time()
            return True

        except Exception as exc:
            logger.error(f"Failed to send reply: {exc}")
            return False

    # -----------------------------------------------------------------------
    # Core: session context (includes scraped order data)
    # -----------------------------------------------------------------------

    async def get_session_context(self, session_id: str) -> dict:
        """Return conversation metadata + scraped order/product info."""
        context = {"channel": self.channel_name, "session_id": session_id}
        cached = self._conversation_cache.get(session_id)
        if cached:
            context["conversation_title"] = cached.get("title", "")
            context["conversation_preview"] = cached.get("preview", "")

        # Try to scrape order cards from chat panel
        order_info = await self._scrape_order_info()
        if order_info:
            context["order_cards"] = order_info

        return context

    # -----------------------------------------------------------------------
    # Order scraping from Xianyu chat
    # -----------------------------------------------------------------------

    async def _scrape_order_info(self) -> list[dict]:
        """Scrape product/order cards visible in the current chat panel."""
        if not self._page:
            return []
        try:
            return await self._page.evaluate(ORDER_SCRAPE_SCRIPT)
        except Exception as exc:
            logger.debug(f"Order scrape failed: {exc}")
            return []

    # -----------------------------------------------------------------------
    # Health check & recovery
    # -----------------------------------------------------------------------

    async def _ensure_healthy(self) -> bool:
        """Check page health; recover if needed."""
        if not self._page:
            return False

        try:
            state = await self._detect_page_state()
        except Exception:
            logger.warning("Page state detection failed — attempting recovery.")
            await self._recover()
            return False

        # Captcha detected
        if state.get("hasCaptcha"):
            logger.warning(
                "Captcha/slider detected! Please solve it manually in the browser. "
                "Waiting 60s..."
            )
            await asyncio.sleep(60)
            return False

        # Login required (session expired)
        if state.get("hasLoginForm") or state.get("hasQRCode"):
            logger.warning("Login form detected — session may have expired.")
            if not state.get("hasConversationList"):
                logger.warning("Waiting for manual re-login (120s)...")
                try:
                    await self._wait_for_any_selector(LOGIN_READY_SELECTORS, timeout=120000)
                    logger.info("Re-login successful.")
                except TimeoutError:
                    logger.error("Re-login timeout.")
                    return False

        # Error page
        if state.get("hasError"):
            logger.warning("Error page detected — reloading...")
            await self._recover()
            return False

        # Blank/stuck page (no conversation list after long time)
        if not state.get("hasConversationList"):
            idle = time.time() - self._last_activity
            if idle > 120:
                logger.warning("Page appears stuck (no conversation list). Recovering...")
                await self._recover()
                return False

        return True

    async def _detect_page_state(self) -> dict:
        """Run JS to detect current page state."""
        if not self._page:
            return {}
        try:
            return await self._page.evaluate(PAGE_STATE_SCRIPT)
        except Exception:
            return {}

    async def _recover(self):
        """Attempt to recover from a broken page state."""
        self._consecutive_errors = 0
        try:
            logger.info("Recovery: reloading Xianyu IM page...")
            await self._navigate_to_im()
        except Exception as exc:
            logger.error(f"Recovery failed: {exc}")

    # -----------------------------------------------------------------------
    # Helpers: navigation & selectors
    # -----------------------------------------------------------------------

    async def _wait_for_any_selector(self, selectors: list[str], timeout: int = 30000):
        if not self._page:
            return
        tasks = [
            self._page.wait_for_selector(sel, timeout=timeout)
            for sel in selectors
        ]
        done, pending = await asyncio.wait(
            [asyncio.ensure_future(t) for t in tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()
        # Check if any succeeded
        for d in done:
            exc = d.exception()
            if exc is None:
                return
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

        preview = (summary.get("preview") or "").strip()
        if preview:
            preview_locator = self._page.get_by_text(preview, exact=False).first
            if await preview_locator.count():
                await preview_locator.click()
                return True

        return False

    async def _activate_conversation(self, session_id: str) -> bool:
        """Open the conversation for a given session_id."""
        cached = self._conversation_cache.get(session_id)
        if cached:
            if await self._open_conversation(cached):
                return True

        conversations = await self._read_conversation_summaries()
        matched = self._match_conversation(session_id, conversations)
        if matched and await self._open_conversation(matched):
            self._conversation_cache[session_id] = matched
            return True

        logger.warning(f"Cannot locate conversation: {session_id}")
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

    async def _fill_input_box_human(self, input_box: Locator, text: str):
        """Fill input with human-like typing delay."""
        if not self._page:
            return
        editable = await input_box.get_attribute("contenteditable")
        tag_name = await input_box.evaluate("(node) => node.tagName.toLowerCase()")
        await input_box.click()
        await self._human_delay(0.1, 0.3)

        if editable == "true" or tag_name != "textarea":
            await input_box.fill("")
            # Type with human-like delays
            for char in text:
                await self._page.keyboard.type(
                    char, delay=HUMAN_TYPING_DELAY + random.randint(-20, 40)
                )
                # Occasional longer pause (thinking)
                if random.random() < 0.05:
                    await self._human_delay(0.2, 0.5)
        else:
            await input_box.fill(text)

    # -----------------------------------------------------------------------
    # Helpers: message dedup & matching
    # -----------------------------------------------------------------------

    def _remember_outgoing(self, session_id: str, text: str):
        payload = {"text": text, "message_id": f"outgoing-{len(self._seen_ids)}"}
        self._seen_ids.add(self._build_message_key(session_id, payload))

    def _mark_payloads_seen(self, session_id: str, payloads: list[dict[str, Any]]) -> int:
        """Mark a batch of payloads as seen without replying."""
        marked = 0
        for payload in payloads:
            message_key = self._build_message_key(session_id, payload)
            if message_key in self._seen_ids:
                continue
            self._seen_ids.add(message_key)
            marked += 1
        return marked

    def _match_conversation(
        self, session_id: str, conversations: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
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
        new_messages = []
        for payload in reversed(payloads):
            if payload.get("outgoing"):
                continue
            message_key = self._build_message_key(session_id, payload)
            if message_key in self._seen_ids:
                break
            new_messages.append(payload)
        new_messages.reverse()
        return new_messages

    @staticmethod
    def _build_message_key(session_id: str, payload: dict[str, Any]) -> str:
        message_id = (payload.get("message_id") or "").strip()
        text = (payload.get("text") or "").strip()
        timestamp = (payload.get("timestamp") or "").strip()
        author = (payload.get("author") or "").strip()
        basis = message_id or f"{author}|{timestamp}|{text}"
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()
        return f"{session_id}:{digest}"

    @staticmethod
    async def _human_delay(min_s: float = 0.3, max_s: float = 0.8):
        """Random delay to mimic human behavior."""
        await asyncio.sleep(random.uniform(min_s, max_s))
