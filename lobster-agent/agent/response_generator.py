"""Generate final reply using an OpenAI-compatible LLM."""

from openai import OpenAI
from loguru import logger

from config.prompts import RESPONSE_GENERATION_PROMPT, SYSTEM_PROMPTS
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


def get_llm_client() -> OpenAI:
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


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
            return "您好，我是小龙虾客服助手，请问有什么可以帮您？"
        return "Hello! I'm Lobster, your customer service assistant. How can I help you?"

    if tool_results and risk_level == "low" and intent != "fallback":
        return tool_results

    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-5:]) if history else "无"
    channel_context_text = _format_channel_context(channel_context or {})
    language = "Chinese" if locale == "zh" else "English"
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
        )
        reply = resp.choices[0].message.content.strip()
        logger.info(f"LLM reply ({OPENAI_MODEL}): {reply[:80]}...")
        return reply
    except Exception as exc:
        logger.error(f"LLM call failed: {exc}")
        if tool_results:
            return tool_results
        if locale == "zh":
            return "抱歉，系统暂时无法处理您的请求，请稍后再试或联系人工客服。"
        return "Sorry, I'm unable to process your request right now. Please try again or contact our support team."


def _format_channel_context(channel_context: dict) -> str:
    if not channel_context:
        return "无"

    ordered_keys = ["conversation_title", "conversation_preview", "session_id", "channel"]
    parts = []
    for key in ordered_keys:
        value = channel_context.get(key)
        if value:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "无"
