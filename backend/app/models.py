from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, now

DEFAULT_HOURS = {day: [["12:00", "15:30"], ["19:00", "23:00"]] for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


class Restaurant(Base):
    __tablename__ = "restaurant"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="My Restaurant")
    phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    about: Mapped[str] = mapped_column(Text, default="")
    hours: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_HOURS))
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    dining_minutes: Mapped[int] = mapped_column(Integer, default=90)
    max_guests: Mapped[int] = mapped_column(Integer, default=12)
    advance_days: Mapped[int] = mapped_column(Integer, default=30)
    prep_target_minutes: Mapped[int] = mapped_column(Integer, default=5)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    user: Mapped[User] = relationship(lazy="joined")


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int] = mapped_column(Integer)
    veg: Mapped[bool] = mapped_column(Boolean, default=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=10)
    other_names: Mapped[str] = mapped_column(String(300), default="")


class DiningTable(Base):
    __tablename__ = "tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    seats: Mapped[int] = mapped_column(Integer)
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class Block(Base):
    __tablename__ = "blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(200), default="")


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    guests: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("tables.id"))
    status: Mapped[str] = mapped_column(String(12), default="confirmed")
    source: Mapped[str] = mapped_column(String(12), default="dashboard")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    qr_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    table: Mapped[DiningTable | None] = relationship(lazy="joined")


class Conversation(Base):
    __tablename__ = "conversations"
    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    history: Mapped[list] = mapped_column(JSON, default=list)
    needs_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SeenMessage(Base):
    __tablename__ = "seen_messages"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)


class Failure(Base):
    __tablename__ = "failures"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), default="", index=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"))
    status: Mapped[str] = mapped_column(String(12), default="open")
    payment_status: Mapped[str] = mapped_column(String(12), default="unpaid")
    total: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(12), default="dashboard")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reservation: Mapped[Reservation | None] = relationship(lazy="joined")
    items: Mapped[list["OrderItem"]] = relationship(lazy="selectin", cascade="all, delete-orphan", order_by="OrderItem.id")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[int | None] = mapped_column(ForeignKey("menu_items.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(String(200), default="")
    menu_item: Mapped[MenuItem | None] = relationship(lazy="joined")
