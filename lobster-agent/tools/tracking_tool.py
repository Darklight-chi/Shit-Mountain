"""Logistics / tracking status tool (mock)."""

from integrations.mock_tracking_service import MockTrackingService

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
