from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import whatsapp
from .auth import current_user
from .db import Session as DbSession
from .db import get_db, now
from .models import WaitlistEntry
from .confirmations import send_confirmation
from .inbox import add_notice
from .reservations import BookingError, book, check_rules, normalize_phone, restaurant

router = APIRouter(prefix="/api/waitlist")
OPEN = ("waiting",)


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


def book_from_waitlist() -> None:
    with DbSession() as db:
        for entry in db.scalars(select(WaitlistEntry).where(WaitlistEntry.status.in_(OPEN), WaitlistEntry.wanted_at <= now())):
            entry.status = "expired"
        db.commit()
        waiting = db.scalars(select(WaitlistEntry.id).where(WaitlistEntry.status == "waiting").order_by(WaitlistEntry.id)).all()
    for entry_id in waiting:
        with DbSession() as db:
            entry = db.get(WaitlistEntry, entry_id)
            try:
                reservation = book(db, name=entry.name, phone=entry.phone, guests=entry.guests, start=entry.wanted_at, source="waitlist")
            except BookingError:
                continue
            entry.status = "booked"
            db.commit()
            add_notice(db, f"{entry.name} was booked from the waitlist for {entry.wanted_at:%a %d %b %I:%M %p}, {entry.guests} guests, "
                           f"ref {reservation.ref}")
            free_window = whatsapp.can_message_freely(db, entry.phone)
            text = (f"Good news {entry.name}, a table freed up and we have booked it for you: {entry.guests} guests at "
                    f"{entry.wanted_at:%I:%M %p on %a %d %b}. Your QR code follows. Reply here if you can't make it.")
            db.commit()
            if free_window:
                try:
                    whatsapp.send_text(entry.phone, text)
                except Exception as e:
                    whatsapp.log_failure(db, "whatsapp_waitlist", f"{entry.phone}: {e}")
        send_confirmation(reservation.id)


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
