from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..conversations.models import CallbackRequest, Conversation
from ..core.errors import DomainError, NotFound
from ..core.events import audit
from ..core.models import Alert, AuditLog
from ..customers.models import Customer
from ..db import get_db
from ..deps import actor, current_user, require
from ..orders.models import Order
from ..reservations.models import Reservation
from ..restaurant.service import day_bounds, get_restaurant, local_now
from . import service

router = APIRouter(prefix="/api", tags=["reporting"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: StaffUser = Depends(current_user)):
    """Numbers for the dashboard home page."""
    r = get_restaurant(db)
    start, end = day_bounds(r, local_now(r).date())
    count = lambda stmt: db.scalar(select(func.count()).select_from(stmt.subquery()))  # noqa: E731
    return {
        "today": local_now(r).date().isoformat(),
        "reservations_today": count(select(Reservation.id).where(Reservation.starts_at >= start, Reservation.starts_at < end,
                                                                 Reservation.status.in_(("held", "confirmed", "arrived", "seated", "completed")))),
        "covers_today": db.scalar(select(func.coalesce(func.sum(Reservation.party_size), 0)).where(
            Reservation.starts_at >= start, Reservation.starts_at < end, Reservation.status.in_(("confirmed", "arrived", "seated", "completed")))),
        "orders_open": count(select(Order.id).where(Order.status.in_(("submitted", "accepted", "preparing", "ready")))),
        "orders_waiting_acceptance": count(select(Order.id).where(Order.status == "submitted")),
        "handoffs_open": count(select(Conversation.id).where(Conversation.mode == "human", Conversation.status == "open")),
        "callbacks_open": count(select(CallbackRequest.id).where(CallbackRequest.status == "open")),
        "alerts_open": count(select(Alert.id).where(Alert.acknowledged_at.is_(None))),
        "ai_enabled": r.ai_enabled, "restaurant": r.name,
    }


@router.get("/usage")
def usage(days: int = 30, db: Session = Depends(get_db), _: StaffUser = Depends(require("usage.view"))):
    return service.usage_summary(db, max(1, min(days, 366)))


@router.get("/health/integrations")
def integration_health(db: Session = Depends(get_db), _: StaffUser = Depends(require("health.view"))):
    return service.health(db)


@router.get("/reports/summary")
def summary(start: date, end: date, db: Session = Depends(get_db), _: StaffUser = Depends(require("reports.view"))):
    if end < start or (end - start).days > 366:
        raise DomainError("Choose a range of up to one year.")
    r = get_restaurant(db)
    return service.report(db, day_bounds(r, start)[0], day_bounds(r, end)[1])


@router.get("/audit")
def audit_log(entity: str | None = None, q: str | None = None, limit: int = 200, db: Session = Depends(get_db),
              _: StaffUser = Depends(require("audit.view"))):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if q:
        stmt = stmt.where(or_(AuditLog.action.ilike(f"%{q}%"), AuditLog.entity_id.ilike(f"%{q}%")))
    return [{"id": a.id, "created_at": a.created_at, "actor_type": a.actor_type, "actor_id": a.actor_id, "action": a.action,
             "entity": a.entity, "entity_id": a.entity_id, "data": a.data, "request_id": a.request_id} for a in db.scalars(stmt)]


@router.get("/customers")
def customers(q: str = "", db: Session = Depends(get_db), _: StaffUser = Depends(require("reservations.view"))):
    stmt = select(Customer).where(Customer.anonymized_at.is_(None)).order_by(Customer.created_at.desc()).limit(100)
    if q:
        stmt = stmt.where(or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
    return [{"id": c.id, "name": c.name, "phone": c.phone, "whatsapp_opt_in": c.whatsapp_opt_in, "created_at": c.created_at}
            for c in db.scalars(stmt)]


@router.get("/customers/{cid}/export")
def export_customer(cid: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("data.manage"))):
    c = db.get(Customer, cid)
    if not c:
        raise NotFound("Customer")
    audit(db, "customer.exported", "customer", c.id, actor=actor(user))
    db.commit()
    return service.export_customer(db, c)


@router.post("/customers/{cid}/anonymize")
def anonymize(cid: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("data.manage"))):
    c = db.get(Customer, cid)
    if not c or c.anonymized_at:
        raise NotFound("Customer")
    service.anonymize_customer(db, c)
    audit(db, "customer.anonymized", "customer", c.id, actor=actor(user))
    db.commit()
    return {"ok": True}


@router.get("/config/export")
def export_config(db: Session = Depends(get_db), user: StaffUser = Depends(require("config.manage"))):
    audit(db, "config.exported", "settings", 1, actor=actor(user))
    db.commit()
    return service.export_config(db)


class ImportIn(BaseModel):
    config: dict
    replace_menu: bool = False


@router.post("/config/import")
def import_config(body: ImportIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("config.manage"))):
    out = service.import_config(db, body.config, replace_menu=body.replace_menu)
    audit(db, "config.imported", "settings", 1, actor=actor(user), **out)
    db.commit()
    return out
