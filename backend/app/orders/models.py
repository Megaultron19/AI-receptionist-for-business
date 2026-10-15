from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..customers.models import Customer
from ..db import Base, utcnow


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("menu_variants.id", ondelete="SET NULL"))
    item_name: Mapped[str] = mapped_column(String(120))
    variant_name: Mapped[str] = mapped_column(String(60), default="")
    addons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(String(300), default="")
    tax_rate_bp: Mapped[int] = mapped_column(Integer)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=10)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(12), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    order_type: Mapped[str] = mapped_column(String(16), default="pickup")
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"))
    scheduled_for: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    special_instructions: Mapped[str] = mapped_column(Text, default="")
    bill: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    subtotal_paise: Mapped[int] = mapped_column(Integer, default=0)
    discount_paise: Mapped[int] = mapped_column(Integer, default=0)
    charges_paise: Mapped[int] = mapped_column(Integer, default=0)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer, default=0)
    amount_due_paise: Mapped[int] = mapped_column(Integer, default=0)
    amount_paid_paise: Mapped[int] = mapped_column(Integer, default=0)
    estimate_minutes: Mapped[int | None] = mapped_column(Integer)
    estimated_ready_at: Mapped[datetime | None]
    invoice_number: Mapped[str | None] = mapped_column(String(32), unique=True)
    customer_gstin: Mapped[str] = mapped_column(String(15), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    confirmed_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    accepted_at: Mapped[datetime | None]
    ready_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str] = mapped_column(String(200), default="")

    customer: Mapped[Customer] = relationship(lazy="joined", innerjoin=True)
    items: Mapped[list[OrderItem]] = relationship(lazy="selectin", order_by=OrderItem.id, cascade="all, delete-orphan")
