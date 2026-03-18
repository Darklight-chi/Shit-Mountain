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
BASELINE_GRACE_SECONDS = 8.0

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
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;

  const normalizeText = (text) => text.replace(/\\s+/g, " ").trim();
  const timeLikePattern = /^(?:\\d{1,2}:\\d{2}|\\d+\\s*(?:分钟前|小时前|天前)|昨天|今天|星期[一二三四五六日天]|刚刚)$/;
  const noiseTexts = new Set(["消息", "通知消息", "系统消息", "闲鱼", "联系卖家", "我的发布", "已读", "未读"]);
  const isVisible = (node) => {
    if (!(node instanceof HTMLElement)) return false;
    const rect = node.getBoundingClientRect();
    const style = window.getComputedStyle(node);
    return (
      rect.width > 20
      && rect.height > 14
      && rect.bottom > 80
      && rect.top < viewportHeight - 90
      && style.visibility !== "hidden"
      && style.display !== "none"
      && style.opacity !== "0"
    );
  };
  const isComposer = (node) => {
    const text = normalizeText(textOf(node));
    const cls = classOf(node).toLowerCase();
    if (node.closest("[role='textbox']")) return true;
    return (
      node.closest("textarea, [contenteditable='true'], form")
      || /enter|发送|输入消息|chat-input|editor|footer/.test(text + " " + cls)
    );
  };
  const composer = document.querySelector("textarea, [contenteditable='true'], [role='textbox']");
  const composerRect = composer?.getBoundingClientRect?.() || null;
  const chatRegionTop = 70;
  const chatRegionBottom = composerRect ? Math.max(chatRegionTop + 120, composerRect.top - 8) : viewportHeight - 110;
  const chatRegionLeft = viewportWidth * 0.22;
  const chatRegionRight = viewportWidth * 0.98;
  const isLikelyChatRegion = (rect) => (
    rect.bottom > chatRegionTop
    && rect.top < chatRegionBottom
    && rect.left > chatRegionLeft
    && rect.right < chatRegionRight
  );
  const isLikelyNoiseText = (text) => (
    !text
    || text.length > 500
    || /^\\d+$/.test(text)
    || timeLikePattern.test(text)
    || noiseTexts.has(text)
  );
  const inferDirection = (node, row) => {
    const nodeRect = node.getBoundingClientRect();
    const rowRect = (row || node).getBoundingClientRect();
    const rect = rowRect.width > nodeRect.width * 1.8 ? nodeRect : rowRect;
    const cls = `${classOf(row).toLowerCase()} ${classOf(node).toLowerCase()}`;
    const avatarNode = row?.querySelector?.("img, [class*='avatar'], [class*='Avatar']");
    if (/(self|mine|owner|seller|me|right|send|outgoing)/.test(cls)) {
      return { outgoing: true, incoming: false };
    }
    if (/(other|buyer|customer|left|receive|incoming)/.test(cls)) {
      return { outgoing: false, incoming: true };
    }
    if (avatarNode instanceof HTMLElement) {
      const avatarRect = avatarNode.getBoundingClientRect();
      const avatarCenter = avatarRect.left + avatarRect.width / 2;
      if (avatarCenter >= viewportWidth * 0.58) {
        return { outgoing: true, incoming: false };
      }
      if (avatarCenter <= viewportWidth * 0.42) {
        return { outgoing: false, incoming: true };
      }
    }
    const leftGap = rect.left;
    const rightGap = viewportWidth - rect.right;
    if (leftGap > rightGap + 40) {
      return { outgoing: true, incoming: false };
    }
    if (rightGap > leftGap + 40) {
      return { outgoing: false, incoming: true };
    }
    const centerX = rect.left + rect.width / 2;
    return centerX >= viewportWidth * 0.58
      ? { outgoing: true, incoming: false }
      : { outgoing: false, incoming: true };
  };

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
    "[role='listitem']",
    "li",
  ];

  const seen = new Set();
  const results = [];
  const pushResult = (node, index, fallback = false) => {
    if (!isVisible(node) || isComposer(node)) return;
    const rawText = normalizeText(textOf(node));
    if (isLikelyNoiseText(rawText)) return;

    const row = node.closest(
      "[data-message-id], [data-mid], [class*='message'], [class*='msg'], [class*='bubble'], li, [role='listitem']"
    ) || node;
    const rect = row.getBoundingClientRect();
    if (!isLikelyChatRegion(rect)) return;
    if (rect.width < 36 || rect.height < 18) return;

    const key = `${dataIdOf(row) || dataIdOf(node)}|${rawText}|${Math.round(rect.top)}`;
    if (seen.has(key)) return;
    seen.add(key);

    const authorNode = row.querySelector("[class*='nick'], [class*='name'], [data-role='name']");
    const timeNode = row.querySelector("time, [class*='time'], [class*='Time']");
    const direction = inferDirection(node, row);

    results.push({
      index,
      text: rawText,
      message_id: dataIdOf(row) || dataIdOf(node) || "",
      author: normalizeText(textOf(authorNode)),
      timestamp: normalizeText(textOf(timeNode)),
      outgoing: direction.outgoing,
      incoming: direction.incoming,
      class_name: classOf(row) || classOf(node),
      top: Math.round(rect.top),
      left: Math.round(rect.left),
      fallback,
    });
  };

  Array.from(document.querySelectorAll(selectors.join(","))).forEach((node, index) => {
    pushResult(node, index, false);
  });

  if (results.length === 0) {
    const fallbackNodes = Array.from(document.querySelectorAll("div, span, p"));
    fallbackNodes.forEach((node, index) => {
      pushResult(node, index, true);
    });
  }

  return results.sort((a, b) => a.index - b.index).slice(-30);
}
"""

# ---------------------------------------------------------------------------
# JS: read conversation list sidebar
# ---------------------------------------------------------------------------
CONVERSATION_LIST_SCRIPT = """
() => {
  const textOf = (node) => (node?.innerText || node?.textContent || "").trim();
  const classOf = (node) => (node?.className && typeof node.className === "string") ? node.className : "";
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  const normalizeText = (text) => text.replace(/\\s+/g, " ").trim();
  const timeLikePattern = /^(?:\\d{1,2}:\\d{2}|\\d+\\s*(?:分钟前|小时前|天前)|昨天|今天|星期[一二三四五六日天]|刚刚)$/;
  const bannedTexts = new Set(["消息", "通知消息", "系统消息", "闲鱼", "联系卖家", "我的发布", "商品", "闲置", "已读", "未读"]);
  const isMeaningfulLine = (line) => {
    if (!line) return false;
    if (bannedTexts.has(line)) return false;
    if (/^\\d+$/.test(line)) return false;
    if (timeLikePattern.test(line)) return false;
    if (/^(?:订单|评价|确认收货|交易成功)/.test(line)) return false;
    return true;
  };
  const extractLines = (node) => (
    normalizeText(textOf(node))
      .split(/\\n+/)
      .flatMap((line) => normalizeText(line).split(/\\s+/))
      .map((line) => normalizeText(line))
      .filter(isMeaningfulLine)
  );
  const isLikelySidebarItem = (node) => {
    if (!(node instanceof HTMLElement)) return false;
    const rect = node.getBoundingClientRect();
    if (rect.width < 120 || rect.height < 36) return false;
    return (
      rect.left < viewportWidth * 0.42
      && rect.right <= viewportWidth * 0.58
      && rect.top >= 60
      && rect.bottom <= viewportHeight - 20
    );
  };
  const isLikelyTitleLine = (line) => (
    isMeaningfulLine(line)
    && line.length <= 24
    && !/[。！？~，,、:：]/.test(line)
  );

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
      if (!isLikelySidebarItem(node)) return null;
      const sessionId = (
        node.getAttribute("data-session-id")
        || node.getAttribute("data-conversation-id")
        || node.getAttribute("data-id")
        || ""
      ).trim();

      const titleNode = node.querySelector("[class*='title'], [class*='name'], [class*='nick'], [class*='Title'], [class*='Name']");
      const previewNode = node.querySelector("[class*='preview'], [class*='snippet'], [class*='last'], [class*='Preview'], [class*='Snippet']");
      const avatarNode = node.querySelector("img, [class*='avatar'], [class*='Avatar']");
      const badgeNode = node.querySelector("[class*='unread'], [class*='badge'], [class*='Unread'], [aria-label*='unread'], [aria-label*='未读']");
      const active = /(active|selected|current)/.test(classOf(node).toLowerCase());

      const titleLines = extractLines(titleNode);
      const previewLines = extractLines(previewNode);
      const nodeLines = extractLines(node);
      const lines = [...titleLines, ...previewLines, ...nodeLines];
      const dedupedLines = lines.filter((line, lineIndex) => lines.indexOf(line) === lineIndex);
      const title = titleLines.find(isLikelyTitleLine)
        || dedupedLines.find(isLikelyTitleLine)
        || titleLines[0]
        || dedupedLines[0]
        || "";
      const preview = previewLines.find((line) => line !== title)
        || dedupedLines.find((line) => line !== title)
        || "";
      const fullText = textOf(node);
      const hasConversationSignals = !!(avatarNode || preview || badgeNode || sessionId);
      const invalidTitle = ["消息", "通知消息", "联系卖家", "闲鱼", "我发布的", "商品", "闲置"].includes(title);
      const invalidTitleClean = !isMeaningfulLine(title);
      const key = sessionId || `${title}-${preview}`;
      if (!title || seen.has(key) || !hasConversationSignals || invalidTitle || invalidTitleClean || fullText === title) return null;
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

SCROLL_CHAT_TO_BOTTOM_SCRIPT = """
() => {
  const selectors = [
    "[class*='message-list']",
    "[class*='MessageList']",
    "[class*='chat-content']",
    "[class*='ChatContent']",
    "[class*='message-content']",
    "[class*='MessageContent']",
    "[class*='scroll']",
    "[class*='Scroll']",
    "[role='log']",
    "[role='main']"
  ];
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;

  for (const node of document.querySelectorAll(selectors.join(","))) {
    if (!(node instanceof HTMLElement)) continue;
    const style = window.getComputedStyle(node);
    const canScroll = node.scrollHeight - node.clientHeight > 80;
    const scrollableY = /(auto|scroll)/.test(style.overflowY || "");
    const rect = node.getBoundingClientRect();
    const inChatArea = rect.top < viewportHeight && rect.bottom > viewportHeight * 0.35;
    if (!canScroll || !scrollableY || !inChatArea) continue;
    node.scrollTop = node.scrollHeight;
  }

  window.scrollTo(0, document.body.scrollHeight);
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
    "[role='textbox']",
    "textarea[placeholder*='输入']",
    "textarea[placeholder*='发送']",
    "[contenteditable='true'][data-placeholder*='输入']",
    "[contenteditable='true'][data-placeholder*='发送']",
    "[contenteditable='true'][placeholder*='输入']",
    "[contenteditable='true'][placeholder*='发送']",
    "[role='textbox'][contenteditable='true']",
    "[role='textbox'][placeholder]",
    "[class*='editor'] [contenteditable='true']",
    "[class*='Editor'] [contenteditable='true']",
    "[class*='input'] textarea",
    "[class*='Input'] textarea",
    "[class*='input'] [contenteditable='true']",
    "[class*='Input'] [contenteditable='true']",
    "[class*='chat-input'] textarea",
    "[class*='ChatInput'] textarea",
    "[class*='chat-input'] [contenteditable='true']",
    "[class*='ChatInput'] [contenteditable='true']",
    "[class*='footer'] textarea",
    "[class*='Footer'] textarea",
    "[class*='footer'] [contenteditable='true']",
    "[class*='Footer'] [contenteditable='true']",
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
        self._startup_at: float = time.time()
        self._conversation_cache: dict[str, dict[str, Any]] = {}
        self._conversation_ids_by_title: dict[str, str] = {}
        self._session_id_aliases: dict[str, str] = {}
        self._recent_replies: dict[str, tuple[str, float]] = {}
        self.last_send_suppressed: bool = False
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

        self._startup_at = time.time()
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
            human_conversations = [
                c for c in conversations if not self._is_non_human_conversation(c)
            ]
            targets = self._select_poll_targets(human_conversations)
            logger.debug(
                "Xianyu poll: total_conversations={} human_conversations={} targets={}",
                len(conversations),
                len(human_conversations),
                [
                    {
                        "title": item.get("title", ""),
                        "unread": item.get("unread", False),
                        "active": item.get("active", False),
                    }
                    for item in targets
                ],
            )

            if not self._baseline_initialized:
                if self._should_wait_for_initial_baseline(targets):
                    return []
                primed = await self._prime_existing_unread_messages(targets[:5]) if targets else 0
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
                new_payloads = self._select_new_incoming_payloads(session_id, payloads)
                if not new_payloads:
                    logger.debug(
                        "Xianyu session '{}' raw payloads: {}",
                        summary.get("title", session_id),
                        [
                            {
                                "text": item.get("text", "")[:50],
                                "message_id": item.get("message_id", ""),
                                "timestamp": item.get("timestamp", ""),
                                "author": item.get("author", ""),
                                "outgoing": item.get("outgoing", False),
                                "fallback": item.get("fallback", False),
                            }
                            for item in payloads[-8:]
                        ],
                    )
                logger.debug(
                    "Xianyu session '{}' -> {} new payload(s): {}",
                    summary.get("title", session_id),
                    len(new_payloads),
                    [
                        {
                            "text": item.get("text", "")[:50],
                            "message_id": item.get("message_id", ""),
                            "timestamp": item.get("timestamp", ""),
                            "author": item.get("author", ""),
                        }
                        for item in new_payloads
                    ],
                )
                for payload in new_payloads:
                    self._seen_ids.add(payload["_message_key"])
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
            if self._is_non_human_conversation(summary):
                continue
            if not await self._open_conversation(summary):
                continue

            await self._human_delay(0.2, 0.4)
            session_id = await self._get_current_session_id(summary)
            summary["session_id"] = session_id
            self._conversation_cache[session_id] = summary
            payloads = await self._read_current_messages()
            primed_count += self._mark_payloads_seen(session_id, payloads)
        return primed_count

    def _should_wait_for_initial_baseline(self, targets: list[dict[str, Any]]) -> bool:
        if targets:
            return False
        return (time.time() - self._startup_at) < BASELINE_GRACE_SECONDS

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
        if self._page.is_closed():
            logger.warning("Xianyu page was closed. Recreating page...")
            await self._recover()
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
            if self._context and (not self._page or self._page.is_closed()):
                self._page = await self._context.new_page()
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
        await self._scroll_chat_to_bottom()
        payloads = await self._page.evaluate(MESSAGE_LIST_SCRIPT)
        return self._collapse_dom_duplicate_payloads(payloads)

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
                    await self._after_open_conversation()
                    return True

        if title:
            title_locator = self._page.get_by_text(title, exact=False).first
            if await title_locator.count():
                await title_locator.click()
                await self._after_open_conversation()
                return True

        preview = (summary.get("preview") or "").strip()
        if preview:
            preview_locator = self._page.get_by_text(preview, exact=False).first
            if await preview_locator.count():
                await preview_locator.click()
                await self._after_open_conversation()
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
        raw_session_id = ""
        if self._page:
            url = self._page.url
            if "sessionId=" in url:
                raw_session_id = url.split("sessionId=", 1)[1].split("&", 1)[0].strip()

        if not raw_session_id:
            raw_session_id = (summary.get("session_id") or "").strip()

        return self._canonicalize_session_id(raw_session_id, summary)

    async def _find_input_box(self) -> Optional[Locator]:
        if not self._page:
            return None
        await self._dismiss_restore_popup()
        for selector in TEXTAREA_SELECTORS:
            locator = self._page.locator(selector)
            count = await locator.count()
            for index in range(count - 1, -1, -1):
                candidate = locator.nth(index)
                if await self._is_candidate_input_box(candidate):
                    return candidate
        return None

    async def _is_candidate_input_box(self, locator: Locator) -> bool:
        try:
            if not await locator.is_visible():
                return False
            box = await locator.bounding_box()
            if not box:
                return False
            viewport = self._page.viewport_size if self._page else None
            viewport_height = (viewport or {}).get("height", 900)
            if box["y"] < viewport_height * 0.45:
                return False
            disabled = await locator.get_attribute("disabled")
            readonly = await locator.get_attribute("readonly")
            role = await locator.get_attribute("role")
            contenteditable = await locator.get_attribute("contenteditable")
            if disabled is not None or readonly is not None:
                return False
            if role not in (None, "textbox") and contenteditable != "true":
                return False
            return True
        except Exception:
            return False

    async def _after_open_conversation(self):
        if not self._page:
            return
        await self._dismiss_restore_popup()
        await self._human_delay(0.1, 0.25)
        await self._scroll_chat_to_bottom()

    async def _dismiss_restore_popup(self):
        if not self._page:
            return

        close_candidates = [
            "button[aria-label='Close']",
            "button[aria-label='关闭']",
            "[class*='modal'] [class*='close']",
            "[class*='Modal'] [class*='close']",
            "[class*='ant-modal'] [aria-label='Close']",
        ]
        for selector in close_candidates:
            locator = self._page.locator(selector).first
            if await locator.count():
                try:
                    await locator.click(timeout=1000)
                    return
                except Exception:
                    continue

        close_texts = ("恢复", "关闭", "取消", "×", "✕")
        for text in close_texts:
            locator = self._page.get_by_text(text, exact=True).first
            if await locator.count():
                try:
                    await locator.click(timeout=1000)
                    return
                except Exception:
                    continue

    async def _scroll_chat_to_bottom(self):
        if not self._page:
            return
        try:
            await self._page.evaluate(SCROLL_CHAT_TO_BOTTOM_SCRIPT)
        except Exception as exc:
            logger.debug(f"Scroll-to-bottom failed: {exc}")

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
        for payload in self._annotate_payload_keys(session_id, payloads):
            message_key = payload["_message_key"]
            if message_key in self._seen_ids:
                continue
            self._seen_ids.add(message_key)
            marked += 1
        return marked

    def _match_conversation(
        self, session_id: str, conversations: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        for summary in conversations:
            candidate_session_id = self._canonicalize_session_id(
                (summary.get("session_id") or "").strip(),
                summary,
            )
            if candidate_session_id == session_id:
                return summary
        cached = self._conversation_cache.get(session_id)
        if not cached:
            return None
        for summary in conversations:
            if summary.get("title") == cached.get("title"):
                return summary
        return None

    def _select_poll_targets(
        self, conversations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        def add_target(summary: dict[str, Any]):
            key = self._conversation_identity_key(summary)
            if not key or key in seen_keys:
                return
            seen_keys.add(key)
            targets.append(summary)

        for summary in conversations:
            if summary.get("unread"):
                add_target(summary)

        for summary in conversations:
            if summary.get("active"):
                add_target(summary)

        if not targets and conversations:
            add_target(conversations[0])

        return targets[:5]

    def _select_new_incoming_payloads(
        self, session_id: str, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        new_messages = []
        annotated_payloads = self._annotate_payload_keys(session_id, payloads)
        for payload in reversed(annotated_payloads):
            if payload.get("outgoing"):
                continue
            if self._is_non_human_message(payload):
                continue
            if self._is_platform_noise(payload):
                continue
            message_key = payload["_message_key"]
            if message_key in self._seen_ids:
                break
            new_messages.append(payload)
        new_messages.reverse()
        return new_messages

    def _annotate_payload_keys(
        self, session_id: str, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        occurrence_counter: dict[str, int] = {}
        annotated: list[dict[str, Any]] = []

        for payload in payloads:
            base_key = self._build_message_key(session_id, payload)
            occurrence_index = occurrence_counter.get(base_key, 0)
            occurrence_counter[base_key] = occurrence_index + 1
            annotated.append(
                {
                    **payload,
                    "_message_key": f"{base_key}:{occurrence_index}",
                }
            )

        return annotated

    @staticmethod
    def _collapse_dom_duplicate_payloads(
        payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        collapsed: list[dict[str, Any]] = []
        seen_keys: list[tuple[str, bool, int]] = []

        for payload in payloads:
            text = (payload.get("text") or "").strip()
            if not text:
                continue

            if payload.get("message_id"):
                collapsed.append(payload)
                continue

            top = int(payload.get("top") or 0)
            outgoing = bool(payload.get("outgoing"))
            duplicate = False
            for existing_text, existing_outgoing, existing_top in seen_keys:
                if (
                    existing_outgoing == outgoing
                    and existing_text == text
                    and abs(existing_top - top) <= 14
                ):
                    duplicate = True
                    break

            if duplicate:
                continue

            seen_keys.append((text, outgoing, top))
            collapsed.append(payload)

        return collapsed

    @staticmethod
    def _is_platform_noise(payload: dict[str, Any]) -> bool:
        text = (payload.get("text") or "").strip()
        if not text:
            return True

        normalized = text.replace("\n", " ")
        platform_noise_markers = (
            "闲鱼币",
            "去领取",
            "立即领取",
            "点击查看",
            "点击查看>",
            "去发布",
            "卖得更快",
            "热卖",
            "加曝光机会",
            "首页的机会",
            "拍张照片就能卖闲置",
            "登录奖励",
            "0元抽",
            "Labubu",
            "AI翻新",
            "本地人",
            "优惠券",
            "即将过期",
            "去使用",
            "年度账单",
            "查看账单",
            "立刻查看",
            "0.01元",
            "兑换",
            "能量",
            "咖啡",
        )
        return any(marker in normalized for marker in platform_noise_markers)

    @staticmethod
    def _is_non_human_message(payload: dict[str, Any]) -> bool:
        text = (payload.get("text") or "").strip()
        author = (payload.get("author") or "").strip()
        normalized = text.replace("\n", " ")

        system_message_markers = (
            "确认收货",
            "交易成功",
            "完成评价",
            "已完成互评",
            "期待你的评价",
            "查看评价",
            "系统消息",
            "官方提醒",
            "订单确认收货奖励",
            "握手",
            "优惠券",
            "年度账单",
            "立刻查看",
            "去使用",
            "去兑换",
        )
        system_author_markers = (
            "工作室",
            "官方",
            "系统",
            "助手",
            "客服",
            "通知",
        )

        return any(marker in normalized for marker in system_message_markers) or any(
            marker in author for marker in system_author_markers
        )

    @staticmethod
    def _is_non_human_conversation(summary: dict[str, Any]) -> bool:
        title = (summary.get("title") or "").strip()
        preview = (summary.get("preview") or "").strip()
        combined = f"{title}\n{preview}"

        conversation_markers = (
            "工作室",
            "通知消息",
            "系统消息",
            "官方",
            "确认收货",
            "完成评价",
            "查看评价",
            "期待你的评价",
            "交易成功",
            "优惠券",
            "年度账单",
            "去兑换",
            "去使用",
        )
        return any(marker in combined for marker in conversation_markers)

    @staticmethod
    def _normalize_title_key(title: str) -> str:
        return " ".join((title or "").split()).strip().lower()

    def _conversation_identity_key(self, summary: dict[str, Any]) -> str:
        session_id = (summary.get("session_id") or "").strip()
        if session_id:
            return self._session_id_aliases.get(session_id, session_id)

        title_key = self._normalize_title_key(summary.get("title", ""))
        if title_key:
            return f"title:{title_key}"

        preview = " ".join((summary.get("preview") or "").split()).strip().lower()
        return f"preview:{preview}" if preview else ""

    def _canonicalize_session_id(self, raw_session_id: str, summary: dict[str, Any]) -> str:
        title_key = self._normalize_title_key(summary.get("title", ""))
        raw_session_id = (raw_session_id or "").strip()

        if raw_session_id and raw_session_id in self._session_id_aliases:
            canonical = self._session_id_aliases[raw_session_id]
            if title_key:
                self._conversation_ids_by_title.setdefault(title_key, canonical)
            return canonical

        if title_key and title_key in self._conversation_ids_by_title:
            canonical = self._conversation_ids_by_title[title_key]
            if raw_session_id:
                self._session_id_aliases[raw_session_id] = canonical
            return canonical

        seed = raw_session_id or title_key or (summary.get("preview") or "").strip()
        if not seed:
            seed = "unknown-session"
        canonical = raw_session_id or f"xianyu_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"

        if raw_session_id:
            self._session_id_aliases[raw_session_id] = canonical
        if title_key:
            self._conversation_ids_by_title[title_key] = canonical
        return canonical

    def _reply_identity(self, session_id: str) -> str:
        cached = self._conversation_cache.get(session_id, {})
        title_key = self._normalize_title_key(cached.get("title", ""))
        if title_key:
            return f"title:{title_key}"
        return self._session_id_aliases.get(session_id, session_id)

    def _should_suppress_duplicate_reply(self, session_id: str, text: str) -> bool:
        identity = self._reply_identity(session_id)
        if not identity:
            return False

        normalized_text = " ".join((text or "").split()).strip()
        if not normalized_text:
            return False

        previous = self._recent_replies.get(identity)
        if not previous:
            return False

        previous_text, sent_at = previous
        return previous_text == normalized_text and (time.time() - sent_at) <= 20

    def _record_recent_reply(self, session_id: str, text: str):
        identity = self._reply_identity(session_id)
        normalized_text = " ".join((text or "").split()).strip()
        if identity and normalized_text:
            self._recent_replies[identity] = (normalized_text, time.time())

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
