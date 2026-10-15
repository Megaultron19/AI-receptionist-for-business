from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..customers.models import Customer
from ..db import Base, utcnow


class Conversation(Base):
    """One WhatsApp thread or one phone call with a customer."""
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(80), index=True)
    mode: Mapped[str] = mapped_column(String(8), default="ai")
    status: Mapped[str] = mapped_column(String(8), default="open")
    handoff_reason: Mapped[str] = mapped_column(String(200), default="")
    handoff_at: Mapped[datetime | None]
    assigned_to: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8), default="")
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_message_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    unread: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship(lazy="joined", innerjoin=True)


class Message(Base):
    """Human-readable record of what was said, for the inbox (separate from the LLM transcript)."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="whatsapp")
    direction: Mapped[str] = mapped_column(String(4))
    sender: Mapped[str] = mapped_column(String(12))
    body: Mapped[str] = mapped_column(Text, default="")
    media: Mapped[str] = mapped_column(String(16), default="")
    template: Mapped[str] = mapped_column(String(100), default="")
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="received")
    error: Mapped[str] = mapped_column(String(300), default="")
    staff_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    provider_call_id: Mapped[str] = mapped_column(String(80), unique=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    from_number: Mapped[str] = mapped_column(String(20), default="")
    to_number: Mapped[str] = mapped_column(String(20), default="")
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    ended_at: Mapped[datetime | None]
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(8), default="")
    turns: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(16), default="in_progress")
    error: Mapped[str] = mapped_column(String(300), default="")


class CallbackRequest(Base):
    __tablename__ = "callback_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    phone: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(16), default="voice")
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    handled_by: Mapped[int | None] = mapped_column(Integer)
    handled_at: Mapped[datetime | None]
    note: Mapped[str] = mapped_column(String(300), default="")

    customer: Mapped[Customer] = relationship(lazy="joined", innerjoin=True)


class Notification(Base):
    """Ledger of customer notifications (confirmations, reminders, payment links...), one row per
    logical message so retries and duplicate jobs never message a customer twice."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="whatsapp")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    method: Mapped[str] = mapped_column(String(16), default="")
    wa_message_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str] = mapped_column(String(300), default="")
    ref_type: Mapped[str] = mapped_column(String(16), default="")
    ref_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    sent_at: Mapped[datetime | None]
