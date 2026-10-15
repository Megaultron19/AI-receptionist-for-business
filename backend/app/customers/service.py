import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..core.errors import DomainError
from ..db import utcnow
from .models import Customer

WHATSAPP_WINDOW = timedelta(hours=24)


def normalize_phone(raw: str, default_country: str = "91") -> str:
    """Return E.164. Accepts '+91 98765 43210', '09876543210', '9876543210', '919876543210', 'whatsapp:+91…'."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = default_country + digits
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise DomainError("Please give a valid phone number.")
    return "+" + digits


def get_or_create(db: Session, phone: str, name: str = "") -> Customer:
    phone = normalize_phone(phone)
    db.execute(insert(Customer).values(phone=phone, name=name.strip()[:120], created_at=utcnow(), language="",
                                       whatsapp_opt_in=False, whatsapp_opt_in_source="", whatsapp_unavailable=False)
               .on_conflict_do_nothing(index_elements=["phone"]))
    c = db.scalar(select(Customer).where(Customer.phone == phone))
    if name.strip() and not c.name:
        c.name = name.strip()[:120]
    return c


def record_opt_in(c: Customer, source: str) -> None:
    if not c.whatsapp_opt_in:
        c.whatsapp_opt_in, c.whatsapp_opt_in_at, c.whatsapp_opt_in_source = True, utcnow(), source


def in_service_window(c: Customer) -> bool:
    return bool(c.last_inbound_whatsapp_at and utcnow() - c.last_inbound_whatsapp_at < WHATSAPP_WINDOW)
