"""Order status lookup tool."""

import re

from integrations.mock_order_service import MockOrderService

order_service = MockOrderService()

STATUS_MAP_ZH = {
    "paid": "已付款，待发货",
    "processing": "处理中",
    "shipped": "已发货",
    "delivered": "已签收",
    "cancelled": "已取消",
}

STATUS_MAP_EN = {
    "paid": "Paid, awaiting shipment",
    "processing": "Processing",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def extract_order_id(message: str) -> str | None:
    """Try to extract an order ID from the message."""
    match = re.search(r"[A-Za-z]\d{4,}", message)
    return match.group(0) if match else None


def resolve_order(message: str, user_id: str = "demo_user") -> dict | None:
    """Resolve an explicit order ID first, otherwise fall back to the latest order for the user."""
    order_id = extract_order_id(message)
    if order_id:
        return order_service.get_order_status(order_id)
    return order_service.get_latest_order_by_user(user_id)


def format_order_summary(order: dict, locale: str = "zh") -> str:
    """Format order data into a customer-facing message."""
    status_map = STATUS_MAP_ZH if locale == "zh" else STATUS_MAP_EN
    status_text = status_map.get(order["status"], order["status"])

    if locale == "zh":
        result = f"订单 {order['order_id']}：{status_text}"
        if order.get("tracking_number"):
            result += f"\n快递单号：{order['tracking_number']}（{order.get('carrier', '')}）"
        if order.get("estimated_delivery"):
            result += f"\n预计送达：{order['estimated_delivery']}"
        return result

    result = f"Order {order['order_id']}: {status_text}"
    if order.get("tracking_number"):
        result += f"\nTracking: {order['tracking_number']} ({order.get('carrier', '')})"
    if order.get("estimated_delivery"):
        result += f"\nEstimated delivery: {order['estimated_delivery']}"
    return result


def query_order(message: str, user_id: str = "demo_user", locale: str = "zh") -> str | None:
    """Look up order status. Returns formatted string or None."""
    order = resolve_order(message, user_id)
    if not order:
        if locale == "zh":
            return "未找到相关订单，请确认订单号后重试。"
        return "Order not found. Please double-check your order number."
    return format_order_summary(order, locale)
