"""SQLAlchemy data models."""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, JSON, Enum
from sqlalchemy.orm import DeclarativeBase
import enum


class Base(DeclarativeBase):
    pass


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String(50), nullable=False)
    session_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    language = Column(String(10), default="zh")
    message_type = Column(String(20), default="text")
    created_at = Column(DateTime, default=datetime.utcnow)
    raw_payload = Column(JSON, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String(50), nullable=False)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    user_id = Column(String(100), nullable=False)
    status = Column(String(20), default=ConversationStatus.ACTIVE.value)
    last_intent = Column(String(50), nullable=True)
    last_risk_level = Column(String(10), default=RiskLevel.LOW.value)
    needs_handoff = Column(Boolean, default=False)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=False)
    summary = Column(Text, nullable=True)
    priority = Column(String(20), default=TicketPriority.MEDIUM.value)
    status = Column(String(20), default=TicketStatus.OPEN.value)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    """Mock order table for demo."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False)
    status = Column(String(30), default="paid")  # paid/processing/shipped/delivered/cancelled
    shipping_status = Column(String(30), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    carrier = Column(String(50), nullable=True)
    estimated_delivery = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    locale = Column(String(10), nullable=False)
    category = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    path = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
