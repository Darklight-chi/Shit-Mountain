"""Mock order service — replace with real API later."""


class OrderService:
    """Unified order service interface."""

    def get_order_status(self, order_id: str) -> dict | None:
        raise NotImplementedError

    def get_latest_order_by_user(self, user_id: str) -> dict | None:
        raise NotImplementedError


class MockOrderService(OrderService):
    """Uses SQLite mock data via OrderRepo."""

    def __init__(self):
        from database.repository import OrderRepo
        self._repo = OrderRepo()

    def get_order_status(self, order_id: str) -> dict | None:
        return self._repo.get_by_order_id(order_id)

    def get_latest_order_by_user(self, user_id: str) -> dict | None:
        return self._repo.get_latest_by_user(user_id)
