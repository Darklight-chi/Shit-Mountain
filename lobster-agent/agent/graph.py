"""LangGraph agent — the core decision engine."""

from agent.state import AgentState
from agent.intent_classifier import classify_intent
from agent.risk_detector import detect_risk
from agent.response_generator import generate_reply
from tools.faq_tool import faq_lookup
from tools.order_tool import query_order
from tools.tracking_tool import query_tracking
from tools.refund_tool import check_refund, check_address_change, check_cancellation
from tools.escalation_tool import escalate
from tools.kb_tool import search_knowledge
from tools.translation_tool import detect_language
from conversation.escalation import EscalationManager
from loguru import logger


def run_agent(context: dict) -> dict:
    """
    Main agent pipeline:
    message → detect language → classify intent → detect risk
    → call tools → generate reply
    Returns: {"reply": str, "intent": str, "risk_level": str, "locale": str, "needs_handoff": bool}
    """
    message = context["message"]
    history = context.get("history", [])
    user_id = context.get("user_id", "demo_user")
    session = context.get("session", {})
    channel_context = context.get("channel_context", {})
    conv_id = session.get("id", 0)

    # Step 1: Detect language
    locale = detect_language(message)
    logger.info(f"Language: {locale}")

    # Step 2: Classify intent
    intent = classify_intent(message)
    logger.info(f"Intent: {intent}")

    # Step 3: Detect risk
    risk_level = detect_risk(message, intent)
    logger.info(f"Risk: {risk_level}")

    # Step 4: High risk → immediate escalation
    if risk_level == "high":
        handoff_msg = escalate(
            conv_id, reason=intent,
            summary=f"High-risk message: {message[:100]}",
            priority="urgent" if "赔偿" in message or "chargeback" in message.lower() else "high",
            locale=locale,
        )
        return {
            "reply": handoff_msg,
            "intent": intent,
            "risk_level": risk_level,
            "locale": locale,
            "needs_handoff": True,
        }

    # Step 5: Call appropriate tool
    tool_results = _call_tool(intent, message, user_id, locale)

    # Step 6: Generate polished reply
    reply = generate_reply(
        message=message, intent=intent, risk_level=risk_level,
        tool_results=tool_results, history=history, locale=locale,
        channel_context=channel_context,
    )

    return {
        "reply": reply,
        "intent": intent,
        "risk_level": risk_level,
        "locale": locale,
        "needs_handoff": False,
    }


def _call_tool(intent: str, message: str, user_id: str, locale: str) -> str:
    """Dispatch to the right tool based on intent."""
    try:
        if intent == "general_greeting":
            return ""  # handled directly in response generator

        if intent == "presale_product":
            # Try FAQ first, then knowledge base
            faq = faq_lookup(message, locale)
            if faq:
                return faq
            return search_knowledge(message, locale)

        if intent == "shipping_time":
            faq = faq_lookup(message, locale)
            return faq or search_knowledge(message, locale)

        if intent == "order_status":
            return query_order(message, user_id, locale)

        if intent == "tracking_status":
            # First check if order has tracking number
            order_result = query_order(message, user_id, locale)
            return order_result or ""

        if intent == "return_refund":
            return check_refund(intent, locale)

        if intent == "address_change":
            return check_address_change("paid", locale)  # Default to pre-ship

        if intent == "cancellation":
            return check_cancellation("paid", locale)

        if intent == "damaged_or_wrong_item":
            return check_refund(intent, locale)

        if intent == "customs_tax":
            return search_knowledge("customs", locale)

        # Fallback: try FAQ then knowledge base
        faq = faq_lookup(message, locale)
        if faq:
            return faq
        return search_knowledge(message, locale)

    except Exception as e:
        logger.error(f"Tool error for intent '{intent}': {e}")
        return ""
