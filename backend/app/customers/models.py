from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, utcnow


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # E.164
    name: Mapped[str] = mapped_column(String(120), default="")
    language: Mapped[str] = mapped_column(String(8), default="")
    # WhatsApp consent: required before we start a conversation (templates); a customer's own
    # inbound message opens the 24h service window regardless.
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_opt_in_at: Mapped[datetime | None]
    whatsapp_opt_in_source: Mapped[str] = mapped_column(String(32), default="")
    whatsapp_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)  # number not on WhatsApp
    last_inbound_whatsapp_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    anonymized_at: Mapped[datetime | None]
