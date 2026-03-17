"""Order status lookup tool."""

import re
from database.repository import OrderRepo

order_repo = OrderRepo()

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
    match = re.search(r'[A-Za-z]\d{4,}', message)
    return match.group(0) if match else None


def query_order(message: str, user_id: str = "demo_user", locale: str = "zh") -> str | None:
    """Look up order status. Returns formatted string or None."""
    order_id = extract_order_id(message)
    status_map = STATUS_MAP_ZH if locale == "zh" else STATUS_MAP_EN

    if order_id:
        order = order_repo.get_by_order_id(order_id)
    else:
        order = order_repo.get_latest_by_user(user_id)

    if not order:
        if locale == "zh":
            return "未找到相关订单，请确认订单号后重试。"
        return "Order not found. Please double-check your order number."

    status_text = status_map.get(order["status"], order["status"])
    if locale == "zh":
        result = f"订单 {order['order_id']}：{status_text}"
        if order.get("tracking_number"):
            result += f"\n快递单号：{order['tracking_number']}（{order.get('carrier', '')}）"
        if order.get("estimated_delivery"):
            result += f"\n预计送达：{order['estimated_delivery']}"
    else:
        result = f"Order {order['order_id']}: {status_text}"
        if order.get("tracking_number"):
            result += f"\nTracking: {order['tracking_number']} ({order.get('carrier', '')})"
        if order.get("estimated_delivery"):
            result += f"\nEstimated delivery: {order['estimated_delivery']}"
    return result
