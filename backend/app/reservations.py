import re
import secrets
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db, now
from .models import Block, DiningTable, Reservation, Restaurant

router = APIRouter(prefix="/api/reservations")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ACTIVE = ("confirmed", "arrived")
NEXT_STATUS = {"confirmed": {"arrived", "cancelled", "no_show"}, "arrived": {"completed"}, "no_show": {"arrived"}}
REF_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class BookingError(Exception):
    def __init__(self, message: str, alternatives: list[datetime] | None = None):
        super().__init__(message)
        self.message = message
        self.alternatives = alternatives or []


def restaurant(db: Session) -> Restaurant:
    r = db.get(Restaurant, 1)
    if not r:
        r = Restaurant(id=1)
        db.add(r)
        db.flush()
    return r


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    if not 10 <= len(digits) <= 15:
        raise BookingError("Please give a valid phone number")
    return "+" + digits


def opening_windows(r: Restaurant, day: date) -> list[tuple[datetime, datetime]]:
    windows = []
    for start, end in r.hours.get(DAYS[day.weekday()], []):
        s = datetime.combine(day, time.fromisoformat(start))
        e = datetime.combine(day, time.fromisoformat(end))
        windows.append((s, e if e > s else e + timedelta(days=1)))
    return windows


def is_open(r: Restaurant, moment: datetime) -> bool:
    for day in (moment.date(), moment.date() - timedelta(days=1)):
        if any(s <= moment < e for s, e in opening_windows(r, day)):
            return True
    return False


def start_times(r: Restaurant, day: date) -> list[datetime]:
    out, length, step = [], timedelta(minutes=r.dining_minutes), timedelta(minutes=r.slot_minutes)
    for s, e in opening_windows(r, day):
        t = s
        while t + length <= e:
            out.append(t)
            t += step
    return out


def free_table(db: Session, guests: int, start: datetime, end: datetime, ignore_id: int | None = None) -> DiningTable | None:
    busy_tables = set(db.scalars(select(Reservation.table_id).where(
        Reservation.status.in_(ACTIVE), Reservation.starts_at < end, Reservation.ends_at > start,
        Reservation.id != (ignore_id or 0))))
    blocks = db.scalars(select(Block.table_id).where(Block.starts_at < end, Block.ends_at > start)).all()
    if None in blocks:
        return None
    busy_tables.update(blocks)
    tables = db.scalars(select(DiningTable).where(DiningTable.available, DiningTable.seats >= guests).order_by(DiningTable.seats, DiningTable.name))
    return next((t for t in tables if t.id not in busy_tables), None)


def check_rules(r: Restaurant, guests: int, start: datetime) -> datetime:
    if guests < 1 or guests > r.max_guests:
        raise BookingError(f"We take bookings for 1 to {r.max_guests} guests. For bigger groups please speak to our staff.")
    if start <= now():
        raise BookingError("That time has already passed")
    if start.date() > now().date() + timedelta(days=r.advance_days):
        raise BookingError(f"We take bookings up to {r.advance_days} days ahead")
    if start not in start_times(r, start.date()):
        raise BookingError("We are not open for a full sitting at that time")
    return start + timedelta(minutes=r.dining_minutes)


def available_times(db: Session, guests: int, day: date) -> list[datetime]:
    r = restaurant(db)
    out = []
    for t in start_times(r, day):
        if t > now() and free_table(db, guests, t, t + timedelta(minutes=r.dining_minutes)):
            out.append(t)
    return out


def nearby_times(db: Session, guests: int, wanted: datetime, count: int = 3) -> list[datetime]:
    return sorted(sorted(available_times(db, guests, wanted.date()), key=lambda t: abs(t - wanted))[:count])


def new_ref(db: Session) -> str:
    while True:
        ref = "".join(secrets.choice(REF_CHARS) for _ in range(6))
        if not db.scalar(select(Reservation.id).where(Reservation.ref == ref)):
            return ref


def book(db: Session, *, name: str, phone: str, guests: int, start: datetime, source: str = "dashboard", notes: str = "") -> Reservation:
    r = restaurant(db)
    end = check_rules(r, guests, start)
    table = free_table(db, guests, start, end)
    if not table:
        raise BookingError("No table is free at that time", nearby_times(db, guests, start))
    reservation = Reservation(ref=new_ref(db), name=name.strip()[:120], phone=normalize_phone(phone), guests=guests,
                              starts_at=start, ends_at=end, table_id=table.id, source=source, notes=notes.strip())
    db.add(reservation)
    db.commit()
    return reservation


def reschedule(db: Session, reservation: Reservation, *, guests: int, start: datetime) -> Reservation:
    if reservation.status != "confirmed":
        raise BookingError("Only confirmed bookings can be changed")
    end = check_rules(restaurant(db), guests, start)
    table = free_table(db, guests, start, end, ignore_id=reservation.id)
    if not table:
        raise BookingError("No table is free at that time", nearby_times(db, guests, start))
    reservation.guests, reservation.starts_at, reservation.ends_at, reservation.table = guests, start, end, table
    db.commit()
    return reservation


def set_status(db: Session, reservation: Reservation, status: str) -> Reservation:
    if status not in NEXT_STATUS.get(reservation.status, set()):
        raise BookingError(f"A {reservation.status.replace('_', ' ')} booking can't be marked {status.replace('_', ' ')}")
    reservation.status = status
    db.commit()
    return reservation


def find(db: Session, ref: str) -> Reservation:
    reservation = db.scalar(select(Reservation).where(Reservation.ref == ref.strip().upper()))
    if not reservation:
        raise HTTPException(404, "Booking not found")
    return reservation


def reservation_out(x: Reservation) -> dict:
    return {"id": x.id, "ref": x.ref, "name": x.name, "phone": x.phone, "guests": x.guests, "starts_at": x.starts_at,
            "ends_at": x.ends_at, "status": x.status, "source": x.source, "notes": x.notes,
            "table": x.table.name if x.table else None}


def http_error(e: BookingError) -> HTTPException:
    return HTTPException(409 if e.alternatives or "No table" in e.message else 400,
                         {"message": e.message, "alternatives": [t.isoformat() for t in e.alternatives]})


class BookingIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str
    guests: int
    starts_at: datetime
    notes: str = Field("", max_length=500)


class ChangeIn(BaseModel):
    guests: int
    starts_at: datetime


@router.get("")
def list_reservations(day: date | None = None, q: str = "", db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(Reservation).order_by(Reservation.starts_at)
    if day:
        start = datetime.combine(day, time.min)
        stmt = stmt.where(Reservation.starts_at >= start, Reservation.starts_at < start + timedelta(days=1))
    if q:
        stmt = stmt.where(or_(Reservation.name.ilike(f"%{q}%"), Reservation.phone.ilike(f"%{q}%"), Reservation.ref.ilike(f"%{q}%")))
    return [reservation_out(x) for x in db.scalars(stmt.limit(500))]


@router.get("/availability")
def availability(day: date, guests: int, db: Session = Depends(get_db), _=Depends(current_user)):
    return [t.strftime("%H:%M") for t in available_times(db, guests, day)]


@router.post("")
def create(body: BookingIn, db: Session = Depends(get_db), _=Depends(current_user)):
    try:
        return reservation_out(book(db, name=body.name, phone=body.phone, guests=body.guests, start=body.starts_at, notes=body.notes))
    except BookingError as e:
        raise http_error(e)


@router.put("/{ref}")
def change(ref: str, body: ChangeIn, db: Session = Depends(get_db), _=Depends(current_user)):
    try:
        return reservation_out(reschedule(db, find(db, ref), guests=body.guests, start=body.starts_at))
    except BookingError as e:
        raise http_error(e)


@router.post("/{ref}/status")
def change_status(ref: str, status: str, db: Session = Depends(get_db), _=Depends(current_user)):
    try:
        return reservation_out(set_status(db, find(db, ref), status))
    except BookingError as e:
        raise http_error(e)
