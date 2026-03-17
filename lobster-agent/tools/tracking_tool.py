"""Logistics / tracking status tool (mock)."""

from integrations.mock_tracking_service import MockTrackingService
from tools.order_tool import resolve_order

tracker = MockTrackingService()


def query_tracking(tracking_number: str, locale: str = "zh") -> str:
    result = tracker.get_tracking_status(tracking_number)
    if not result:
        if locale == "zh":
            return "未找到该物流单号的信息，请核实后再试。"
        return "Tracking number not found. Please verify and try again."

    if locale == "zh":
        lines = [
            f"快递公司：{result['carrier']}",
            f"当前状态：{result['status']}",
            f"最新轨迹：{result['latest_event']}",
        ]
        if result.get("estimated_delivery"):
            lines.append(f"预计送达：{result['estimated_delivery']}")
    else:
        lines = [
            f"Carrier: {result['carrier']}",
            f"Status: {result['status']}",
            f"Latest: {result['latest_event']}",
        ]
        if result.get("estimated_delivery"):
            lines.append(f"ETA: {result['estimated_delivery']}")
    return "\n".join(lines)


def query_tracking_for_order(message: str, user_id: str = "demo_user", locale: str = "zh") -> str:
    """Resolve an order from the message and return tracking details when available."""
    order = resolve_order(message, user_id)
    if not order:
        if locale == "zh":
            return "未找到相关订单，请确认订单号后重试。"
        return "Order not found. Please double-check your order number."

    tracking_number = order.get("tracking_number")
    if not tracking_number:
        if locale == "zh":
            return f"订单 {order['order_id']} 目前还没有物流单号，通常是还未出库或承运商尚未回传。"
        return (
            f"Order {order['order_id']} does not have a tracking number yet. "
            "It is likely still being prepared or awaiting carrier sync."
        )

    return query_tracking(tracking_number, locale)
