"""Database initialization and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import DATABASE_URL
from database.models import Base, Order
from loguru import logger


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables and seed mock data."""
    Base.metadata.create_all(engine)
    logger.info("Database tables created.")
    _seed_mock_orders()


def get_session():
    """Get a new database session."""
    return SessionLocal()


def _seed_mock_orders():
    """Insert demo orders if table is empty."""
    session = SessionLocal()
    try:
        if session.query(Order).count() == 0:
            mock_orders = [
                Order(
                    order_id="A10239",
                    user_id="demo_user",
                    status="shipped",
                    shipping_status="in_transit",
                    tracking_number="SF1234567890",
                    carrier="顺丰速运",
                    estimated_delivery="2026-03-20",
                    address="上海市浦东新区xxx路123号",
                ),
                Order(
                    order_id="A10240",
                    user_id="demo_user",
                    status="paid",
                    shipping_status="pending",
                    tracking_number=None,
                    carrier=None,
                    estimated_delivery="2026-03-22",
                    address="北京市朝阳区xxx街456号",
                ),
                Order(
                    order_id="A10241",
                    user_id="demo_user",
                    status="delivered",
                    shipping_status="delivered",
                    tracking_number="YT9876543210",
                    carrier="圆通快递",
                    estimated_delivery="2026-03-15",
                    address="广州市天河区xxx大道789号",
                ),
                Order(
                    order_id="B20001",
                    user_id="en_user",
                    status="shipped",
                    shipping_status="in_transit",
                    tracking_number="UPS1Z999AA10123456784",
                    carrier="UPS",
                    estimated_delivery="2026-03-21",
                    address="123 Main St, New York, NY 10001",
                ),
            ]
            session.add_all(mock_orders)
            session.commit()
            logger.info(f"Seeded {len(mock_orders)} mock orders.")
    finally:
        session.close()
