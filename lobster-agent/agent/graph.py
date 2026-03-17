"""LangGraph agent — the core decision engine."""

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
from loguru import logger


def run_agent(context: dict) -> dict:
    """
    Main agent pipeline:
    message -> detect language -> classify intent -> detect risk
    -> call tools -> generate reply
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

    # Step 4: High risk -> immediate escalation
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

    # Step 5: Call appropriate tool (with channel context for live order data)
    tool_results = _call_tool(intent, message, user_id, locale, channel_context)

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


def _call_tool(intent: str, message: str, user_id: str, locale: str,
               channel_context: dict = None) -> str:
    """Dispatch to the right tool based on intent."""
    try:
        if intent == "general_greeting":
            return ""  # handled directly in response generator

        if intent == "presale_product":
            # Check if we have product info from the chat (Xianyu order cards)
            product_info = _extract_order_card_info(channel_context)
            if product_info:
                return product_info
            # Try FAQ first, then knowledge base
            faq = faq_lookup(message, locale)
            if faq:
                return faq
            return search_knowledge(message, locale)

        if intent == "shipping_time":
            faq = faq_lookup(message, locale)
            return faq or search_knowledge(message, locale)

        if intent == "order_status":
            # Try live order data from channel first
            live_order = _extract_order_card_info(channel_context)
            if live_order:
                return live_order
            return query_order(message, user_id, locale)

        if intent == "tracking_status":
            live_order = _extract_order_card_info(channel_context)
            if live_order:
                return live_order
            order_result = query_order(message, user_id, locale)
            return order_result or ""

        if intent == "return_refund":
            return check_refund(intent, locale)

        if intent == "address_change":
            # Try to determine order status from channel context
            order_status = _detect_order_status(channel_context)
            return check_address_change(order_status, locale)

        if intent == "cancellation":
            order_status = _detect_order_status(channel_context)
            return check_cancellation(order_status, locale)

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


def _extract_order_card_info(channel_context: dict = None) -> str:
    """Extract order/product info from Xianyu scraped order cards."""
    if not channel_context:
        return ""
    order_cards = channel_context.get("order_cards", [])
    if not order_cards:
        return ""

    parts = []
    for card in order_cards[-3:]:  # Last 3 cards max
        title = card.get("title", "")
        price = card.get("price", "")
        status = card.get("status", "")
        if title:
            line = f"商品: {title}"
            if price:
                line += f" | 价格: {price}元"
            if status:
                line += f" | 状态: {status}"
            parts.append(line)

    return "\n".join(parts) if parts else ""


def _detect_order_status(channel_context: dict = None) -> str:
    """Try to detect order status from scraped order cards."""
    if not channel_context:
        return "paid"
    order_cards = channel_context.get("order_cards", [])
    if not order_cards:
        return "paid"

    latest = order_cards[-1]
    status = latest.get("status", "")

    # Map Xianyu status text to internal status
    if "已发货" in status or "运输" in status:
        return "shipped"
    if "已完成" in status or "交易成功" in status or "已签收" in status:
        return "delivered"
    if "已取消" in status:
        return "cancelled"
    return "paid"
