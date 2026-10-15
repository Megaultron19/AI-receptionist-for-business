from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, utcnow

DEFAULT_HOURS = {d: [["12:00", "15:30"], ["19:00", "23:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


class RestaurantSettings(Base):
    """Single row (id=1): this installation's restaurant. Validated through schemas.SettingsIn."""
    __tablename__ = "restaurant_settings"
    id: Mapped[int] = mapped_column(primary_key=True)

    # Profile
    name: Mapped[str] = mapped_column(String(200), default="My Restaurant")
    name_pronunciation: Mapped[str] = mapped_column(String(200), default="")  # how the voice agent should say it
    legal_name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(100), default="")
    state_code: Mapped[str] = mapped_column(String(4), default="")  # GST state code, e.g. 27 for Maharashtra
    pincode: Mapped[str] = mapped_column(String(10), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    maps_url: Mapped[str] = mapped_column(String(500), default="")
    gstin: Mapped[str] = mapped_column(String(15), default="")
    fssai_license: Mapped[str] = mapped_column(String(20), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    arrival_instructions: Mapped[str] = mapped_column(Text, default="")
    pickup_instructions: Mapped[str] = mapped_column(Text, default="")

    # AI receptionist
    languages: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["en-IN", "hi-IN"])
    primary_language: Mapped[str] = mapped_column(String(8), default="en-IN")
    greeting_en: Mapped[str] = mapped_column(Text, default="")
    greeting_hi: Mapped[str] = mapped_column(Text, default="")
    ai_knowledge: Mapped[str] = mapped_column(Text, default="")  # approved facts: parking, policies, FAQ
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    transfer_number: Mapped[str] = mapped_column(String(20), default="")
    staff_alert_numbers: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Hours
    opening_hours: Mapped[dict[str, list[list[str]]]] = mapped_column(JSON, default=lambda: dict(DEFAULT_HOURS))

    # Reservation rules
    reservations_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    slot_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    default_duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    duration_rules: Mapped[list[dict[str, int]]] = mapped_column(JSON, default=lambda: [{"min_party": 7, "minutes": 120}])
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    min_notice_minutes: Mapped[int] = mapped_column(Integer, default=30)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=30)
    min_party: Mapped[int] = mapped_column(Integer, default=1)
    max_party: Mapped[int] = mapped_column(Integer, default=12)
    hold_minutes: Mapped[int] = mapped_column(Integer, default=15)  # deposit holds and waitlist offers
    deposit_per_guest_paise: Mapped[int] = mapped_column(Integer, default=0)
    deposit_min_party: Mapped[int] = mapped_column(Integer, default=0)  # 0 = deposits off
    cancellation_cutoff_minutes: Mapped[int] = mapped_column(Integer, default=120)  # customer self-cancel/reschedule
    cancellation_policy: Mapped[str] = mapped_column(Text, default="")
    no_show_grace_minutes: Mapped[int] = mapped_column(Integer, default=30)
    reminder_offsets_minutes: Mapped[list[int]] = mapped_column(JSON, default=lambda: [1440, 120])
    reminder_channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["whatsapp"])

    # Ordering
    ordering_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    prep_target_minutes: Mapped[int] = mapped_column(Integer, default=5)
    kitchen_parallel_orders: Mapped[int] = mapped_column(Integer, default=4)
    max_active_orders: Mapped[int] = mapped_column(Integer, default=25)
    auto_accept_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    min_payment_type: Mapped[str] = mapped_column(String(8), default="full")  # full | percent | flat | none
    min_payment_value: Mapped[int] = mapped_column(Integer, default=0)  # basis points for percent, paise for flat
    default_tax_rate_bp: Mapped[int] = mapped_column(Integer, default=500)  # 5% GST = 2.5% CGST + 2.5% SGST
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, default=False)
    charges: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    discounts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    invoice_prefix: Mapped[str] = mapped_column(String(16), default="INV")
    next_invoice_number: Mapped[int] = mapped_column(Integer, default=1)

    # WhatsApp template names (approved in Meta) for messages outside the 24h service window
    whatsapp_templates: Mapped[dict[str, dict[str, str]]] = mapped_column(JSON, default=dict)

    # Data retention
    transcript_retention_days: Mapped[int] = mapped_column(Integer, default=180)

    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class SpecialDay(Base):
    """Holiday / exceptional closure / special hours for one date (overrides opening_hours)."""
    __tablename__ = "special_days"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=True)
    intervals: Mapped[list[list[str]]] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(String(200), default="")
