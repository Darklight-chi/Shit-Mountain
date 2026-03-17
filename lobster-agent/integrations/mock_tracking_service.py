"""Mock tracking / logistics service."""


class TrackingService:
    """Unified tracking interface."""

    def get_tracking_status(self, tracking_number: str) -> dict | None:
        raise NotImplementedError


class MockTrackingService(TrackingService):
    """Returns hardcoded tracking data for demo."""

    MOCK_DATA = {
        "SF1234567890": {
            "carrier": "顺丰速运",
            "status": "运输中",
            "latest_event": "2026-03-17 08:30 包裹已到达上海转运中心",
            "estimated_delivery": "2026-03-20",
        },
        "YT9876543210": {
            "carrier": "圆通快递",
            "status": "已签收",
            "latest_event": "2026-03-15 14:22 已签收，签收人：本人",
            "estimated_delivery": "2026-03-15",
        },
        "UPS1Z999AA10123456784": {
            "carrier": "UPS",
            "status": "In Transit",
            "latest_event": "2026-03-17 06:00 Departed facility in Shenzhen, CN",
            "estimated_delivery": "2026-03-21",
        },
    }

    def get_tracking_status(self, tracking_number: str) -> dict | None:
        return self.MOCK_DATA.get(tracking_number)
