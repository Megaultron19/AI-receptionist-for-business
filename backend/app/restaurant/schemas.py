import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def check_intervals(intervals: list[list[str]]) -> list[list[str]]:
    for iv in intervals:
        if len(iv) != 2 or not all(HHMM.match(t) for t in iv) or iv[0] == iv[1]:
            raise ValueError("each interval must be [\"HH:MM\", \"HH:MM\"] (end before start = past midnight)")
    return intervals


class Charge(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["percent", "flat"]
    value: int = Field(ge=0)
    taxable: bool = True
    applies_to: Literal["all", "pickup", "dine_in"] = "all"


class Discount(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    percent_bp: int = Field(gt=0, le=10000)
    min_subtotal_paise: int = Field(ge=0, default=0)
    active: bool = True


class DurationRule(BaseModel):
    min_party: int = Field(ge=1)
    minutes: int = Field(ge=15, le=600)


class Template(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    language: str = Field(default="en", max_length=10)


class SettingsIn(BaseModel):
    """All fields optional: PATCH semantics."""
    name: str | None = Field(None, min_length=1, max_length=200)
    name_pronunciation: str | None = Field(None, max_length=200)
    legal_name: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    state_code: str | None = Field(None, pattern=r"^(\d{2})?$")
    pincode: str | None = Field(None, pattern=r"^(\d{6})?$")
    phone: str | None = None
    maps_url: str | None = Field(None, max_length=500)
    gstin: str | None = None
    fssai_license: str | None = Field(None, pattern=r"^(\d{14})?$")
    timezone: str | None = None
    arrival_instructions: str | None = Field(None, max_length=1000)
    pickup_instructions: str | None = Field(None, max_length=1000)

    languages: list[Literal["en-IN", "hi-IN"]] | None = Field(None, min_length=1)
    primary_language: Literal["en-IN", "hi-IN"] | None = None
    greeting_en: str | None = Field(None, max_length=500)
    greeting_hi: str | None = Field(None, max_length=500)
    ai_knowledge: str | None = Field(None, max_length=20000)
    ai_enabled: bool | None = None
    transfer_number: str | None = None
    staff_alert_numbers: list[str] | None = None

    opening_hours: dict[str, list[list[str]]] | None = None

    reservations_enabled: bool | None = None
    slot_interval_minutes: Literal[5, 10, 15, 20, 30, 60] | None = None
    default_duration_minutes: int | None = Field(None, ge=15, le=600)
    duration_rules: list[DurationRule] | None = None
    buffer_minutes: int | None = Field(None, ge=0, le=120)
    min_notice_minutes: int | None = Field(None, ge=0, le=10080)
    max_advance_days: int | None = Field(None, ge=0, le=365)
    min_party: int | None = Field(None, ge=1, le=100)
    max_party: int | None = Field(None, ge=1, le=200)
    hold_minutes: int | None = Field(None, ge=5, le=1440)
    deposit_per_guest_paise: int | None = Field(None, ge=0)
    deposit_min_party: int | None = Field(None, ge=0)
    cancellation_cutoff_minutes: int | None = Field(None, ge=0, le=10080)
    cancellation_policy: str | None = Field(None, max_length=2000)
    no_show_grace_minutes: int | None = Field(None, ge=5, le=240)
    reminder_offsets_minutes: list[int] | None = None
    reminder_channels: list[Literal["whatsapp"]] | None = None

    ordering_enabled: bool | None = None
    prep_target_minutes: int | None = Field(None, ge=1, le=240)
    kitchen_parallel_orders: int | None = Field(None, ge=1, le=100)
    max_active_orders: int | None = Field(None, ge=1, le=1000)
    auto_accept_orders: bool | None = None
    min_payment_type: Literal["full", "percent", "flat", "none"] | None = None
    min_payment_value: int | None = Field(None, ge=0)
    default_tax_rate_bp: int | None = Field(None, ge=0, le=5000)
    prices_include_tax: bool | None = None
    charges: list[Charge] | None = None
    discounts: list[Discount] | None = None
    invoice_prefix: str | None = Field(None, pattern=r"^[A-Za-z0-9/-]{1,16}$")

    whatsapp_templates: dict[Literal["booking_confirmation", "booking_reminder", "waitlist_offer", "payment_link",
                                     "order_update", "cancellation", "staff_alert"], Template] | None = None
    transcript_retention_days: int | None = Field(None, ge=7, le=3650)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("unknown timezone, e.g. Asia/Kolkata")
        return v

    @field_validator("phone", "transfer_number")
    @classmethod
    def _phone(cls, v):
        if v and not E164.match(v):
            raise ValueError("use international format, e.g. +919876543210")
        return v

    @field_validator("staff_alert_numbers")
    @classmethod
    def _phones(cls, v):
        for p in v or []:
            if not E164.match(p):
                raise ValueError(f"{p}: use international format, e.g. +919876543210")
        return v

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        if v and not GSTIN.match(v.upper()):
            raise ValueError("GSTIN must be 15 characters, e.g. 27ABCDE1234F1Z5")
        return v.upper() if v else v

    @field_validator("opening_hours")
    @classmethod
    def _hours(cls, v):
        if v is None:
            return v
        if set(v) - set(DAYS):
            raise ValueError(f"days must be among {DAYS}")
        return {d: check_intervals(v.get(d, [])) for d in DAYS}

    @field_validator("reminder_offsets_minutes")
    @classmethod
    def _offsets(cls, v):
        if v is not None and (len(v) > 4 or any(not 15 <= m <= 10080 for m in v)):
            raise ValueError("up to 4 reminders, each 15 minutes to 7 days before")
        return v

    @model_validator(mode="after")
    def _cross(self):
        if self.min_payment_type == "percent" and self.min_payment_value is not None and self.min_payment_value > 10000:
            raise ValueError("percent minimum payment is in basis points (10000 = 100%)")
        return self


class SpecialDayIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    closed: bool = True
    intervals: list[list[str]] = []
    note: str = Field("", max_length=200)

    @field_validator("intervals")
    @classmethod
    def _iv(cls, v):
        return check_intervals(v)
