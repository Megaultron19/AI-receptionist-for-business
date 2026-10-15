from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, utcnow


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(16), unique=True)  # our receipt id, sent to Razorpay
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="requested")  # requested | pending | processed | failed
    provider_refund_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Payment(Base):
    """One Razorpay payment link. Status only moves to 'paid' after we fetch the link from Razorpay and
    see it paid in full — never on a webhook body, a customer message or a screenshot alone."""
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(16), unique=True)  # sent as reference_id; idempotency key
    purpose: Mapped[str] = mapped_column(String(16))  # order | deposit
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    # creating | created | pending | paid | failed | expired | cancelled | refunded | partially_refunded
    status: Mapped[str] = mapped_column(String(20), default="creating", index=True)
    provider: Mapped[str] = mapped_column(String(16), default="razorpay")
    provider_link_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(40))
    short_url: Mapped[str] = mapped_column(String(300), default="")
    expires_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    last_failure: Mapped[str] = mapped_column(String(300), default="")
    refunded_paise: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    last_synced_at: Mapped[datetime | None]

    refunds: Mapped[list[Refund]] = relationship(lazy="selectin", order_by=Refund.id)
