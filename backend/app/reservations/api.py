from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..auth.permissions import can
from ..core.errors import Conflict, DomainError, NotFound
from ..core.events import audit
from ..customers.models import Customer
from ..customers.service import get_or_create
from ..db import get_db
from ..deps import actor, require
from ..restaurant.service import day_bounds, get_restaurant, parse_time, tz
from . import engine
from .models import Reservation, WaitlistEntry

router = APIRouter(prefix="/api", tags=["reservations"])


def res_out(res: Reservation) -> dict:
    return {
        "id": res.id, "ref": res.ref, "status": res.status, "party_size": res.party_size,
        "starts_at": res.starts_at, "ends_at": res.ends_at, "source": res.source, "notes": res.notes,
        "staff_notes": res.staff_notes, "hold_reason": res.hold_reason, "hold_expires_at": res.hold_expires_at,
        "deposit_paise": res.deposit_paise, "created_at": res.created_at, "arrived_at": res.arrived_at,
        "seated_at": res.seated_at, "completed_at": res.completed_at, "cancelled_at": res.cancelled_at,
        "cancel_reason": res.cancel_reason,
        "customer": {"id": res.customer.id, "name": res.customer.name, "phone": res.customer.phone},
        "table_ids": sorted({a.table_id for a in res.allocations if a.active}),
    }


class ReservationIn(BaseModel):
    phone: str
    name: str = Field("", max_length=120)
    party_size: int = Field(ge=1, le=200)
    starts_at: str
    notes: str = Field("", max_length=1000)
    table_ids: list[int] | None = None


class ReservationPatch(BaseModel):
    starts_at: str | None = None
    party_size: int | None = Field(None, ge=1, le=200)
    table_ids: list[int] | None = None
    notes: str | None = Field(None, max_length=1000)
    staff_notes: str | None = Field(None, max_length=1000)


class StatusIn(BaseModel):
    status: str
    reason: str = Field("", max_length=200)


class WaitlistIn(BaseModel):
    phone: str
    name: str = Field("", max_length=120)
    party_size: int = Field(ge=1, le=200)
    earliest: str
    latest: str
    notes: str = Field("", max_length=500)


def alternatives_error(db: Session, party: int, start, msg: str) -> DomainError:
    alts = engine.suggest_alternatives(db, party, start, staff=True)
    zone = tz(get_restaurant(db))
    nearby = ", ".join(a.astimezone(zone).strftime("%a %d %b %H:%M") for a in alts)
    return Conflict(msg + (f" Free times nearby: {nearby}" if nearby else ""))


@router.get("/reservations")
def list_reservations(day: date | None = None, status: str | None = None, q: str | None = None,
                      db: Session = Depends(get_db), _: StaffUser = Depends(require("reservations.view"))):
    r = get_restaurant(db)
    stmt = select(Reservation).join(Customer).order_by(Reservation.starts_at)
    if day:
        start, end = day_bounds(r, day)
        stmt = stmt.where(Reservation.starts_at >= start, Reservation.starts_at < end)
    if status:
        stmt = stmt.where(Reservation.status.in_(status.split(",")))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Reservation.ref.ilike(like), Customer.name.ilike(like), Customer.phone.ilike(like)))
    return [res_out(x) for x in db.scalars(stmt.limit(500))]


@router.get("/reservations/availability")
def availability(day: date, party_size: int, db: Session = Depends(get_db), _: StaffUser = Depends(require("reservations.view"))):
    return {"times": engine.available_times(db, party_size, day, staff=True),
            "options": [{"label": o.label, "capacity": o.capacity, "table_ids": o.table_ids}
                        for o in engine.table_options(db, party_size)]}


@router.post("/reservations")
def create(body: ReservationIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("reservations.manage"))):
    r = get_restaurant(db)
    start = parse_time(r, body.starts_at)
    customer = get_or_create(db, body.phone, body.name)
    try:
        res = engine.create_reservation(db, customer=customer, party=body.party_size, start=start, source="dashboard",
                                        actor=actor(user), notes=body.notes, staff=True, table_ids=body.table_ids)
    except Conflict as e:
        db.rollback()
        raise alternatives_error(db, body.party_size, start, e.message)
    db.commit()
    return res_out(res)


@router.get("/reservations/{ref}")
def read(ref: str, db: Session = Depends(get_db), _: StaffUser = Depends(require("reservations.view"))):
    return res_out(engine.get_by_ref(db, ref))


@router.patch("/reservations/{ref}")
def update(ref: str, body: ReservationPatch, db: Session = Depends(get_db), user: StaffUser = Depends(require("reservations.manage"))):
    r = get_restaurant(db)
    res = engine.get_by_ref(db, ref, for_update=True)
    if body.notes is not None:
        res.notes = body.notes
    if body.staff_notes is not None:
        res.staff_notes = body.staff_notes
    if body.starts_at or body.party_size or body.table_ids is not None:
        start = parse_time(r, body.starts_at) if body.starts_at else res.starts_at
        party = body.party_size or res.party_size
        try:
            engine.reschedule(db, res, start=start, party=party, actor=actor(user), staff=True, table_ids=body.table_ids or None)
        except Conflict as e:
            db.rollback()
            raise alternatives_error(db, party, start, e.message)
    db.commit()
    return res_out(res)


@router.post("/reservations/{ref}/status")
def set_status(ref: str, body: StatusIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("reservations.arrival"))):
    if body.status in ("cancelled", "confirmed") and not can(user.role, "reservations.manage"):
        raise DomainError("You don't have permission to do that.", "forbidden", 403)
    res = engine.get_by_ref(db, ref, for_update=True)
    if body.status == "confirmed" and res.status == "held":
        engine.confirm_hold(db, res, actor=actor(user))
    else:
        engine.transition(db, res, body.status, actor=actor(user), reason=body.reason or ("cancelled by staff" if body.status == "cancelled" else ""))
    db.commit()
    return res_out(res)


def wl_out(e: WaitlistEntry) -> dict:
    return {"id": e.id, "day": e.day.isoformat(), "earliest": e.earliest, "latest": e.latest, "party_size": e.party_size,
            "status": e.status, "reservation_id": e.reservation_id, "notes": e.notes, "created_at": e.created_at,
            "customer": {"name": e.customer.name, "phone": e.customer.phone}}


@router.get("/waitlist")
def list_waitlist(day: date, db: Session = Depends(get_db), _: StaffUser = Depends(require("reservations.view"))):
    return [wl_out(e) for e in db.scalars(select(WaitlistEntry).where(WaitlistEntry.day == day).order_by(WaitlistEntry.created_at))]


@router.post("/waitlist")
def add_waitlist(body: WaitlistIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("waitlist.manage"))):
    r = get_restaurant(db)
    customer = get_or_create(db, body.phone, body.name)
    e = engine.add_to_waitlist(db, customer=customer, party=body.party_size, earliest=parse_time(r, body.earliest),
                               latest=parse_time(r, body.latest), source="dashboard", actor=actor(user), notes=body.notes)
    db.commit()
    return wl_out(e)


@router.post("/waitlist/{entry_id}/cancel")
def cancel_waitlist(entry_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("waitlist.manage"))):
    e = db.get(WaitlistEntry, entry_id)
    if not e:
        raise NotFound("Waitlist entry")
    if e.status not in ("waiting", "offered"):
        raise DomainError(f"Entry is already {e.status}.")
    if e.status == "offered" and e.reservation_id:
        res = db.get(Reservation, e.reservation_id)
        if res.status == "held":
            engine.transition(db, res, "cancelled", actor=actor(user), reason="waitlist entry cancelled")
    e.status = "cancelled"
    audit(db, "waitlist.cancelled", "waitlist", e.id, actor=actor(user))
    db.commit()
    return wl_out(e)
