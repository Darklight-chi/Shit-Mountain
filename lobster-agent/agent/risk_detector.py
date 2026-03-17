"""Risk level detection — keyword-first, LLM fallback."""

from config.policies import ESCALATION_TRIGGERS
from loguru import logger

MEDIUM_KEYWORDS = [
    "退货", "退款", "换货", "发错", "坏了", "少件", "破损",
    "return", "refund", "exchange", "wrong item", "damaged", "missing",
]


def detect_risk(message: str, intent: str = "") -> str:
    """Detect risk level: low / medium / high."""
    msg = message.lower()

    # High risk — escalation triggers
    for trigger in ESCALATION_TRIGGERS:
        if trigger.lower() in msg:
            logger.warning(f"HIGH risk detected — trigger: '{trigger}'")
            return "high"

    # High risk by intent
    if intent == "complaint":
        return "high"

    # Medium risk — after-sales
    for kw in MEDIUM_KEYWORDS:
        if kw in msg:
            return "medium"

    if intent in ("return_refund", "damaged_or_wrong_item", "customs_tax"):
        return "medium"

    return "low"
