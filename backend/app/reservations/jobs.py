from datetime import date

from sqlalchemy.orm import Session

from ..core.events import alert
from ..core.jobs import handler, periodic
from ..db import utcnow
from . import engine
from .models import Reservation


@handler("reservation.hold_expire")
def hold_expire(db: Session, payload: dict) -> None:
    res = db.get(Reservation, payload["id"], with_for_update=True)
    if res:
        engine.expire_hold(db, res)


@handler("reservation.no_show_check")
def no_show_check(db: Session, payload: dict) -> None:
    res = db.get(Reservation, payload["id"], with_for_update=True)
    # Ignore stale jobs from before a reschedule.
    if res and res.status == "confirmed" and int(res.starts_at.timestamp()) == payload["starts_at"] and res.starts_at < utcnow():
        engine.transition(db, res, "no_show", actor=("system", None), reason="not checked in within grace period")
        alert(db, "no_show", f"{res.ref} ({res.customer.name or res.customer.phone}, {res.party_size} guests) marked no-show.",
              ref=("reservation", res.ref))


@handler("waitlist.process")
def waitlist_process(db: Session, payload: dict) -> None:
    engine.process_waitlist(db, date.fromisoformat(payload["day"]))
