"""Agent orchestration and tool dispatch."""

from loguru import logger

from agent.intent_classifier import classify_intent
from agent.response_generator import generate_reply
from agent.risk_detector import detect_risk
from conversation.escalation import EscalationManager
from tools.escalation_tool import escalate
from tools.faq_tool import faq_lookup
from tools.kb_tool import search_knowledge
from tools.order_tool import query_order, resolve_order
from tools.refund_tool import check_address_change, check_cancellation, check_refund
from tools.tracking_tool import query_tracking_for_order
from tools.translation_tool import detect_language


OPERATIONS_CHANNELS = {"xianyu", "ozon"}
FOLLOW_UP_NUDGES_ZH = {"在吗", "还在吗", "有人吗", "在不在", "还在不", "你好", "您好"}
FOLLOW_UP_NUDGES_EN = {"hi", "hello", "hey", "any update", "are you there", "still there"}
RESUMABLE_INTENTS = {
    "order_status",
    "tracking_status",
    "shipping_time",
    "return_refund",
    "damaged_or_wrong_item",
    "address_change",
    "cancellation",
    "customs_tax",
}
MANUAL_REVIEW_INTENTS = {"address_change", "cancellation"}
AUTO_REPLY_DURING_HANDOFF_INTENTS = {
    "order_status",
    "tracking_status",
    "shipping_time",
    "presale_product",
}


def run_agent(context: dict) -> dict:
    """Run the end-to-end agent pipeline."""
    channel = context.get("channel", "")
    channel_context = context.get("channel_context", {})
    message = _normalize_customer_message(context["message"], channel, channel_context)
    history = context.get("history", [])
    user_id = context.get("user_id", "demo_user")
    session = context.get("session", {})
    conv_id = session.get("id", 0)
    order = resolve_order(message, user_id)

    locale = detect_language(message)
    logger.info(f"Language: {locale}")

    raw_intent = classify_intent(message)
    intent = _recover_follow_up_intent(channel, message, raw_intent, session)
    logger.info(f"Intent: {intent}")

    risk_level = detect_risk(message, intent)
    logger.info(f"Risk: {risk_level}")

    if (
        session.get("needs_handoff")
        and channel in OPERATIONS_CHANNELS
        and _should_keep_existing_handoff(intent, risk_level)
    ):
        return _build_handoff_result(
            locale=locale,
            intent=intent,
            risk_level=risk_level,
            summary=_build_session_summary(channel, intent, risk_level, message, order, True),
        )

    operational_handoff = _check_operational_handoff(
        channel=channel,
        message=message,
        session=session,
        history=history,
        intent=intent,
        risk_level=risk_level,
        order=order,
        conv_id=conv_id,
        locale=locale,
    )
    if operational_handoff:
        return operational_handoff

    if risk_level == "high":
        handoff_msg = escalate(
            conv_id,
            reason=intent,
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
            "summary": _build_session_summary(channel, intent, risk_level, message, order, True),
        }

    tool_results = _call_tool(intent, message, user_id, locale, channel_context, order)
    reply = generate_reply(
        message=message,
        intent=intent,
        risk_level=risk_level,
        tool_results=tool_results,
        history=history,
        locale=locale,
        channel_context=channel_context,
    )

    return {
        "reply": reply,
        "intent": intent,
        "risk_level": risk_level,
        "locale": locale,
        "needs_handoff": False,
        "summary": _build_session_summary(channel, intent, risk_level, message, order, False),
    }


def _call_tool(
    intent: str,
    message: str,
    user_id: str,
    locale: str,
    channel_context: dict | None = None,
    order: dict | None = None,
) -> str:
    """Dispatch to the right tool based on intent."""
    try:
        if intent == "general_greeting":
            return ""

        if intent == "presale_product":
            price_reply = _build_price_negotiation_reply(message, locale, channel_context)
            if price_reply:
                return price_reply
            product_info = _extract_order_card_info(channel_context)
            if product_info:
                return product_info
            faq = faq_lookup(message, locale)
            if faq:
                return faq
            return search_knowledge(message, locale)

        if intent == "shipping_time":
            faq = faq_lookup(message, locale)
            return faq or search_knowledge(message, locale)

        if intent == "order_status":
            live_order = _extract_order_card_info(channel_context)
            if live_order:
                return live_order
            return query_order(message, user_id, locale)

        if intent == "tracking_status":
            live_order = _extract_order_card_info(channel_context)
            if live_order:
                return live_order
            return query_tracking_for_order(message, user_id, locale)

        if intent == "return_refund":
            return check_refund(intent, locale)

        if intent == "address_change":
            return check_address_change(_detect_order_status(channel_context, order), locale)

        if intent == "cancellation":
            return check_cancellation(_detect_order_status(channel_context, order), locale)

        if intent == "damaged_or_wrong_item":
            return check_refund(intent, locale)

        if intent == "customs_tax":
            return search_knowledge("customs", locale)

        faq = faq_lookup(message, locale)
        if faq:
            return faq
        return search_knowledge(message, locale)

    except Exception as exc:
        logger.error(f"Tool error for intent '{intent}': {exc}")
        return ""


def _recover_follow_up_intent(channel: str, message: str, intent: str, session: dict) -> str:
    """Resume the previous issue when the user only nudges for an update."""
    if channel not in OPERATIONS_CHANNELS or intent != "general_greeting":
        return intent

    last_intent = session.get("last_intent")
    if last_intent not in RESUMABLE_INTENTS:
        return intent

    normalized = message.strip().lower()
    if normalized in FOLLOW_UP_NUDGES_ZH or normalized in FOLLOW_UP_NUDGES_EN:
        return last_intent
    return intent


def _check_operational_handoff(
    channel: str,
    message: str,
    session: dict,
    history: list[dict],
    intent: str,
    risk_level: str,
    order: dict | None,
    conv_id: int,
    locale: str,
) -> dict | None:
    """Apply xianyu / ozon operational rules before normal auto-reply."""
    if channel not in OPERATIONS_CHANNELS:
        return None

    recent_user_turns = sum(1 for item in history if item.get("role") == "user")
    last_intent = session.get("last_intent")

    if intent == "fallback" and last_intent == "fallback" and recent_user_turns >= 3:
        return _handoff_with_ticket(
            conv_id=conv_id,
            locale=locale,
            intent=intent,
            risk_level="medium",
            priority="medium",
            reason="fallback_unresolved",
            summary=f"Unresolved conversation after repeated fallback: {message[:100]}",
            channel=channel,
            order=order,
            message=message,
        )

    if (
        intent in MANUAL_REVIEW_INTENTS
        and order
        and order.get("status") in {"shipped", "delivered", "cancelled"}
    ):
        return _handoff_with_ticket(
            conv_id=conv_id,
            locale=locale,
            intent=intent,
            risk_level="medium",
            priority="high",
            reason=f"{intent}_{order['status']}",
            summary=f"Manual review needed for order {order['order_id']} ({order['status']}): {message[:100]}",
            channel=channel,
            order=order,
            message=message,
        )

    if (
        intent in {"return_refund", "damaged_or_wrong_item", "customs_tax"}
        and last_intent == intent
        and recent_user_turns >= 3
        and risk_level == "medium"
    ):
        return _handoff_with_ticket(
            conv_id=conv_id,
            locale=locale,
            intent=intent,
            risk_level=risk_level,
            priority="medium",
            reason=f"{intent}_repeated",
            summary=f"Repeated after-sales issue requiring follow-up: {message[:100]}",
            channel=channel,
            order=order,
            message=message,
        )

    return None


def _should_keep_existing_handoff(intent: str, risk_level: str) -> bool:
    """Only keep an existing handoff pinned for intents we still should not auto-handle."""
    if risk_level == "high":
        return True
    if intent in AUTO_REPLY_DURING_HANDOFF_INTENTS:
        return False
    return True


def _handoff_with_ticket(
    conv_id: int,
    locale: str,
    intent: str,
    risk_level: str,
    priority: str,
    reason: str,
    summary: str,
    channel: str,
    order: dict | None,
    message: str,
) -> dict:
    reply = escalate(
        conv_id,
        reason=reason,
        summary=summary,
        priority=priority,
        locale=locale,
    )
    return {
        "reply": reply,
        "intent": intent,
        "risk_level": risk_level,
        "locale": locale,
        "needs_handoff": True,
        "summary": _build_session_summary(channel, intent, risk_level, message, order, True),
    }


def _build_handoff_result(locale: str, intent: str, risk_level: str, summary: str) -> dict:
    """Return an existing handoff message without creating a duplicate ticket."""
    return {
        "reply": EscalationManager.handoff_message(locale),
        "intent": intent,
        "risk_level": risk_level,
        "locale": locale,
        "needs_handoff": True,
        "summary": summary,
    }


def _extract_order_card_info(channel_context: dict | None = None) -> str:
    """Extract order/product info from scraped order cards."""
    if not channel_context:
        return ""

    order_cards = channel_context.get("order_cards", [])
    if not order_cards:
        return ""

    parts = []
    for card in order_cards[-3:]:
        title = card.get("title", "")
        price = card.get("price", "")
        status = card.get("status", "")
        if not title:
            continue
        line = f"商品：{title}"
        if price:
            line += f" | 价格：{price}"
        if status:
            line += f" | 状态：{status}"
        parts.append(line)

    return "\n".join(parts)


def _build_price_negotiation_reply(
    message: str,
    locale: str,
    channel_context: dict | None = None,
) -> str:
    normalized = message.lower()
    markers_zh = (
        "便宜",
        "低一点",
        "少一点",
        "最低",
        "还能少",
        "议价",
        "砍价",
        "抹零",
        "刀吗",
    )
    if locale == "zh" and any(marker in normalized for marker in markers_zh):
        order_cards = (channel_context or {}).get("order_cards", [])
        latest_card = order_cards[-1] if order_cards else {}
        price = (latest_card.get("price") or "").strip()
        if price:
            return f"亲，这边标的就是现在能给到的实在价了，当前这款是{price}元，空间确实不大啦，真心想要的话我给您尽快安排~"
        return "亲，这边已经是比较实在的价格啦，空间确实不大，真心想要的话我这边可以优先给您安排~"

    if locale == "en" and any(marker in normalized for marker in ("discount", "best price", "lower", "cheaper")):
        return "This is already a pretty fair price, so there is not much room left. If you really want it, I can help arrange it quickly."

    return ""


def _normalize_customer_message(
    message: str,
    channel: str,
    channel_context: dict | None = None,
) -> str:
    """Trim channel-specific noise from scraped text before intent/risk handling."""
    cleaned = (message or "").strip()
    if not cleaned:
        return ""

    if channel == "xianyu":
        title = ((channel_context or {}).get("conversation_title") or "").strip()
        if title and cleaned.startswith(title):
            stripped = cleaned[len(title):].strip(" :：,-，。！？!?")
            if stripped:
                cleaned = stripped
        for suffix in ("已读", "未读"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()

    return cleaned


def _detect_order_status(channel_context: dict | None = None, order: dict | None = None) -> str:
    """Try to detect order status from scraped order cards, then fall back to the order record."""
    if not channel_context:
        return (order or {}).get("status", "paid")

    order_cards = channel_context.get("order_cards", [])
    if not order_cards:
        return (order or {}).get("status", "paid")

    latest = order_cards[-1]
    status = latest.get("status", "")

    if "已发货" in status or "运输" in status:
        return "shipped"
    if "已完成" in status or "交易成功" in status or "已签收" in status:
        return "delivered"
    if "已取消" in status:
        return "cancelled"
    return (order or {}).get("status", "paid")


def _build_session_summary(
    channel: str,
    intent: str,
    risk_level: str,
    message: str,
    order: dict | None,
    needs_handoff: bool,
) -> str:
    """Build a compact operation summary for dashboards and handoff review."""
    parts = [f"channel={channel}", f"intent={intent}", f"risk={risk_level}"]
    if needs_handoff:
        parts.append("handoff=yes")
    if order and order.get("order_id"):
        parts.append(f"order={order['order_id']}")
        parts.append(f"order_status={order.get('status', '')}")
    parts.append(f"latest={message[:60]}")
    return " | ".join(parts)
