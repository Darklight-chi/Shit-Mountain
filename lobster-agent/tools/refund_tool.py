"""Refund / return policy tool."""

from config.policies import REFUND_POLICY


def check_refund(intent: str, locale: str = "zh") -> str:
    """Return refund guidance based on sub-intent."""
    policy = REFUND_POLICY.get(locale, REFUND_POLICY["zh"])

    if intent == "damaged_or_wrong_item":
        # Try to give more specific guidance
        return policy.get("damaged", policy["within_7_days"])

    # Default: general return/refund info
    return policy["within_7_days"]


def check_address_change(order_status: str, locale: str = "zh") -> str:
    from config.policies import ADDRESS_CHANGE_POLICY
    policy = ADDRESS_CHANGE_POLICY.get(locale, ADDRESS_CHANGE_POLICY["zh"])
    if order_status in ("paid", "processing"):
        return policy["before_ship"]
    return policy["after_ship"]


def check_cancellation(order_status: str, locale: str = "zh") -> str:
    from config.policies import CANCELLATION_POLICY
    policy = CANCELLATION_POLICY.get(locale, CANCELLATION_POLICY["zh"])
    if order_status in ("paid", "processing"):
        return policy["before_ship"]
    return policy["after_ship"]
