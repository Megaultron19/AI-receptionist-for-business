from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import whatsapp
from .auth import current_user
from .db import Session as DbSession
from .db import get_db, now
from .models import WaitlistEntry
from .reservations import BookingError, check_rules, free_table, normalize_phone, restaurant

router = APIRouter(prefix="/api/waitlist")
OPEN = ("waiting", "offered")


def join(db: Session, *, name: str, phone: str, guests: int, wanted_at: datetime) -> WaitlistEntry:
    check_rules(restaurant(db), guests, wanted_at)
    phone = normalize_phone(phone)
    entry = db.scalar(select(WaitlistEntry).where(WaitlistEntry.phone == phone, WaitlistEntry.wanted_at == wanted_at,
                                                  WaitlistEntry.status.in_(OPEN)))
    if not entry:
        entry = WaitlistEntry(name=name.strip()[:120], phone=phone, guests=guests, wanted_at=wanted_at, status="waiting")
        db.add(entry)
        db.commit()
    return entry


def mark_booked(db: Session, phone: str, day) -> None:
    for entry in db.scalars(select(WaitlistEntry).where(WaitlistEntry.phone == phone, WaitlistEntry.status.in_(OPEN))):
        if entry.wanted_at.date() == day:
            entry.status = "booked"
    db.commit()


def offer_free_tables() -> None:
    with DbSession() as db:
        dining = timedelta(minutes=restaurant(db).dining_minutes)
        for entry in db.scalars(select(WaitlistEntry).where(WaitlistEntry.status.in_(OPEN), WaitlistEntry.wanted_at <= now())):
            entry.status = "expired"
        db.commit()
        waiting = db.scalars(select(WaitlistEntry).where(WaitlistEntry.status == "waiting").order_by(WaitlistEntry.id)).all()
        offers = []
        for entry in waiting:
            if free_table(db, entry.guests, entry.wanted_at, entry.wanted_at + dining):
                entry.status = "offered"
                free_window = whatsapp.can_message_freely(db, entry.phone)
                offers.append((entry.phone, free_window, f"Good news {entry.name}, a table for {entry.guests} at "
                               f"{entry.wanted_at:%I:%M %p on %a %d %b} is now free. Reply here to book it before someone else does."))
        db.commit()
        for phone, free_window, text in offers:
            try:
                if not free_window:
                    raise whatsapp.WhatsAppError("customer has not messaged in 24 hours")
                whatsapp.send_text(phone, text)
            except Exception as e:
                whatsapp.log_failure(db, "whatsapp_waitlist", f"{phone}: {e}")


def entry_out(e: WaitlistEntry) -> dict:
    return {"id": e.id, "name": e.name, "phone": e.phone, "guests": e.guests, "wanted_at": e.wanted_at, "status": e.status}


class EntryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str
    guests: int
    wanted_at: datetime


@router.get("")
def list_entries(db: Session = Depends(get_db), _=Depends(current_user)):
    rows = db.scalars(select(WaitlistEntry).where(WaitlistEntry.status.in_(OPEN), WaitlistEntry.wanted_at > now()).order_by(WaitlistEntry.wanted_at))
    return [entry_out(e) for e in rows]


@router.post("")
def add(body: EntryIn, db: Session = Depends(get_db), _=Depends(current_user)):
    try:
        return entry_out(join(db, name=body.name, phone=body.phone, guests=body.guests, wanted_at=body.wanted_at))
    except BookingError as e:
        raise HTTPException(409, e.message)


@router.delete("/{entry_id}")
def remove(entry_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    entry = db.get(WaitlistEntry, entry_id)
    if not entry:
        raise HTTPException(404, "Not on the waitlist")
    entry.status = "removed"
    db.commit()
    return {"ok": True}
