from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..customers.models import Customer
from ..db import Base, utcnow
from ..tables.models import TableAllocation

ACTIVE_STATUSES = ("held", "confirmed", "arrived", "seated")


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(12), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    party_size: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(index=True)
    ends_at: Mapped[datetime]
    # held (awaiting deposit / waitlist offer) | confirmed | arrived | seated | completed | cancelled | no_show
    status: Mapped[str] = mapped_column(String(16), index=True)
    hold_reason: Mapped[str | None] = mapped_column(String(16))  # deposit | waitlist
    hold_expires_at: Mapped[datetime | None]
    source: Mapped[str] = mapped_column(String(16))  # voice | whatsapp | dashboard | waitlist
    notes: Mapped[str] = mapped_column(Text, default="")  # customer special requests
    staff_notes: Mapped[str] = mapped_column(Text, default="")
    deposit_paise: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    confirmed_at: Mapped[datetime | None]
    arrived_at: Mapped[datetime | None]
    seated_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str] = mapped_column(String(200), default="")

    customer: Mapped[Customer] = relationship(lazy="joined")
    allocations: Mapped[list[TableAllocation]] = relationship(lazy="selectin")


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    day: Mapped[date] = mapped_column(Date)
    earliest: Mapped[datetime]
    latest: Mapped[datetime]
    party_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="waiting")  # waiting | offered | booked | expired | cancelled
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"))
    source: Mapped[str] = mapped_column(String(16), default="dashboard")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    customer: Mapped[Customer] = relationship(lazy="joined")

    __table_args__ = (Index("ix_waitlist_day_status", "day", "status"),)
