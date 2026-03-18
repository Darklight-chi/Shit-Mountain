"""Generate final reply using an OpenAI-compatible LLM (OpenClaw / Ollama / OpenAI)."""

import random
from openai import OpenAI
from loguru import logger

from config.prompts import RESPONSE_GENERATION_PROMPT, SYSTEM_PROMPTS, XIANYU_GREETINGS_ZH
from config.settings import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENCLAW_AGENT_ID,
    LLM_TIMEOUT_SECONDS,
)


def get_llm_client() -> OpenAI:
    extra = {}
    if OPENCLAW_AGENT_ID:
        extra["default_headers"] = {"x-openclaw-agent-id": OPENCLAW_AGENT_ID}
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, **extra)


def generate_reply(
    message: str,
    intent: str,
    risk_level: str,
    tool_results: str,
    history: list[dict],
    locale: str = "zh",
    channel_context: dict | None = None,
) -> str:
    """Generate a polished customer service reply via LLM."""
    if intent == "general_greeting":
        if locale == "zh":
            return random.choice(XIANYU_GREETINGS_ZH)
        return "Hi there! What can I help you with?"

    if tool_results and risk_level == "low" and intent in {
        "order_status",
        "tracking_status",
        "return_refund",
        "address_change",
        "cancellation",
        "damaged_or_wrong_item",
        "customs_tax",
    }:
        return tool_results

    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-5:]) if history else "无"
    channel_context_text = _format_channel_context(channel_context or {})
    lang_map = {"zh": "Chinese", "en": "English", "ru": "Russian"}
    language = lang_map.get(locale, "Chinese")
    user_prompt = RESPONSE_GENERATION_PROMPT.format(
        locale=locale,
        intent=intent,
        risk_level=risk_level,
        tool_results=tool_results or "无",
        channel_context=channel_context_text,
        history=history_text,
        message=message,
        language=language,
    )

    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS.get(locale, SYSTEM_PROMPTS["zh"])},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=300,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        reply = resp.choices[0].message.content.strip()
        logger.info(f"LLM reply ({OPENAI_MODEL}): {reply[:80]}...")
        return reply
    except Exception as exc:
        logger.error(f"LLM call failed: {exc}")
        if tool_results:
            return tool_results
        if locale == "zh" and intent == "presale_product":
            return "亲，您说的这个我先帮您看下，您也可以直接说下最关心价格、成色还是发货哈~"
        if locale == "zh":
            return "抱歉，系统暂时无法处理您的请求，请稍后再试或联系人工客服。"
        return "Sorry, I'm unable to process your request right now. Please try again or contact our support team."


def _format_channel_context(channel_context: dict) -> str:
    if not channel_context:
        return "无"

    parts = []
    for key in ("conversation_title", "conversation_preview", "session_id", "channel"):
        value = channel_context.get(key)
        if value:
            parts.append(f"{key}={value}")

    # Include scraped order/product card info
    order_cards = channel_context.get("order_cards", [])
    if order_cards:
        for card in order_cards[-3:]:
            card_desc = card.get("title", "")
            if card.get("price"):
                card_desc += f" ({card['price']}元)"
            if card.get("status"):
                card_desc += f" [{card['status']}]"
            if card_desc:
                parts.append(f"商品卡片: {card_desc}")

    return ", ".join(parts) if parts else "无"
