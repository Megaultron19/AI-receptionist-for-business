from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..core.errors import DomainError, NotFound
from ..core.events import audit
from ..db import get_db
from ..deps import actor, current_user, require
from .models import RestaurantSettings, SpecialDay
from .schemas import SettingsIn, SpecialDayIn
from .service import get_restaurant

router = APIRouter(prefix="/api", tags=["restaurant"])

PUBLIC_FIELDS = [c.name for c in RestaurantSettings.__table__.columns if c.name not in ("id",)]


def settings_out(r: RestaurantSettings) -> dict:
    return {f: getattr(r, f) for f in PUBLIC_FIELDS}


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), _: StaffUser = Depends(current_user)):
    r = get_restaurant(db)
    db.commit()
    return settings_out(r)


@router.patch("/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("settings.manage"))):
    r = get_restaurant(db, for_update=True)
    changes = body.model_dump(exclude_unset=True, mode="json")
    if (changes.get("min_party", r.min_party)) > (changes.get("max_party", r.max_party)):
        raise DomainError("Minimum party size can't exceed maximum party size.")
    for k, v in changes.items():
        setattr(r, k, v)
    audit(db, "settings.updated", "settings", 1, actor=actor(user), fields=sorted(changes))
    db.commit()
    return settings_out(r)


def special_out(s: SpecialDay) -> dict:
    return {"id": s.id, "day": s.day.isoformat(), "closed": s.closed, "intervals": s.intervals, "note": s.note}


@router.get("/special-days")
def list_special_days(db: Session = Depends(get_db), _: StaffUser = Depends(current_user)):
    return [special_out(s) for s in db.scalars(select(SpecialDay).order_by(SpecialDay.day))]


@router.put("/special-days")
def upsert_special_day(body: SpecialDayIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("settings.manage"))):
    if not body.closed and not body.intervals:
        raise DomainError("Give special opening hours, or mark the day closed.")
    day = date.fromisoformat(body.day)
    s = db.scalar(select(SpecialDay).where(SpecialDay.day == day)) or SpecialDay(day=day)
    s.closed, s.intervals, s.note = body.closed, [] if body.closed else body.intervals, body.note
    db.add(s)
    audit(db, "special_day.saved", "special_day", body.day, actor=actor(user), closed=body.closed)
    db.commit()
    return special_out(s)


@router.delete("/special-days/{special_id}")
def delete_special_day(special_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("settings.manage"))):
    s = db.get(SpecialDay, special_id)
    if not s:
        raise NotFound("Special day")
    audit(db, "special_day.deleted", "special_day", s.day.isoformat(), actor=actor(user))
    db.delete(s)
    db.commit()
    return {"ok": True}
