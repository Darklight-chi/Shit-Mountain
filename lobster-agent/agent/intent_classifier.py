"""Intent classification — keyword-first, LLM fallback."""

import re
from loguru import logger

# Keyword rules ordered by specificity (more specific first)
# (intent, zh_keywords, en_keywords)
# English keywords use word-boundary matching; Chinese uses substring matching
KEYWORD_RULES = [
    ("complaint", ["投诉", "举报", "骗", "差评", "赔偿", "骗子", "法律"],
     ["complaint", "scam", "fraud", "sue", "chargeback", "dispute", "bad review"]),
    ("customs_tax", ["海关", "扣关", "关税", "被税", "清关"],
     ["customs", "duty", "detained"]),
    ("damaged_or_wrong_item", ["发错", "坏了", "少件", "破损", "质量问题", "缺件"],
     ["wrong item", "damaged", "broken", "missing item", "defective"]),
    ("return_refund", ["退货", "退款", "退吗", "可以退", "怎么退"],
     ["return", "refund", "send back", "money back"]),
    ("tracking_status", ["物流", "快递", "到哪了", "还没到", "单号", "运单"],
     ["tracking", "where is my", "shipment", "logistics", "delivery status"]),
    ("order_status", ["订单", "下单", "查单", "查订单"],
     ["order status", "my order", "check order", "order number"]),
    ("address_change", ["改地址", "地址错", "修改地址", "换地址"],
     ["change address", "wrong address", "update address"]),
    ("cancellation", ["取消", "不要了", "取消订单"],
     ["cancel order", "cancel my"]),
    ("shipping_time", ["多久发货", "什么时候发", "几天到", "多久到", "发货时间"],
     ["when ship", "shipping time", "how long", "when deliver"]),
    ("presale_product", ["有货", "现货", "尺寸", "怎么用", "区别", "材质", "颜色", "款式", "优惠"],
     ["in stock", "available", "size", "how to use", "difference", "material", "color", "discount"]),
    ("general_greeting", ["在吗", "你好", "嗨"],
     ["hello", "hey"]),
]

# Short-message-only greetings (exact or near-exact match)
GREETING_EXACT = {"hi", "hello", "hey", "在吗", "你好", "嗨", "hi!", "hello!"}


def classify_intent(message: str) -> str:
    """Classify intent using keyword matching. Returns intent string."""
    msg = message.lower().strip()

    # Exact match for very short messages (greetings)
    if msg in GREETING_EXACT or len(msg) <= 3 and msg in ("hi", "hey", "嗨", "在吗"):
        logger.debug(f"Intent exact match greeting: '{msg}'")
        return "general_greeting"

    # Rule-based matching (ordered by priority)
    for intent, zh_kw, en_kw in KEYWORD_RULES:
        for kw in zh_kw:
            if kw in msg:
                logger.debug(f"Intent matched by zh keyword '{kw}': {intent}")
                return intent
        for kw in en_kw:
            # For English, use word boundary matching to avoid "hi" in "this"
            if re.search(r'\b' + re.escape(kw) + r'\b', msg):
                logger.debug(f"Intent matched by en keyword '{kw}': {intent}")
                return intent

    return "fallback"
