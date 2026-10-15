from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..auth.permissions import can
from ..core.errors import DomainError
from ..customers.models import Customer
from ..customers.service import get_or_create
from ..db import get_db
from ..deps import actor, require
from ..payments.models import Payment
from ..restaurant.service import day_bounds, get_restaurant, parse_time
from . import service
from .models import Order

router = APIRouter(prefix="/api/orders", tags=["orders"])


def order_out(o: Order, payments: list[Payment] | None = None) -> dict:
    return {
        "id": o.id, "ref": o.ref, "status": o.status, "channel": o.channel, "order_type": o.order_type,
        "reservation_id": o.reservation_id, "scheduled_for": o.scheduled_for, "special_instructions": o.special_instructions,
        "bill": o.bill, "subtotal_paise": o.subtotal_paise, "discount_paise": o.discount_paise, "charges_paise": o.charges_paise,
        "tax_paise": o.tax_paise, "total_paise": o.total_paise, "amount_due_paise": o.amount_due_paise,
        "amount_paid_paise": o.amount_paid_paise, "estimate_minutes": o.estimate_minutes,
        "estimated_ready_at": o.estimated_ready_at, "invoice_number": o.invoice_number, "customer_gstin": o.customer_gstin,
        "created_at": o.created_at, "accepted_at": o.accepted_at, "ready_at": o.ready_at, "completed_at": o.completed_at,
        "cancelled_at": o.cancelled_at, "cancel_reason": o.cancel_reason,
        "customer": {"id": o.customer.id, "name": o.customer.name, "phone": o.customer.phone},
        "items": [{"id": l.id, "menu_item_id": l.menu_item_id, "variant_id": l.variant_id, "item_name": l.item_name,
                   "variant_name": l.variant_name, "addons": l.addons, "quantity": l.quantity,
                   "unit_price_paise": l.unit_price_paise, "line_total_paise": l.unit_price_paise * l.quantity,
                   "instructions": l.instructions} for l in o.items],
        "payments": [{"ref": p.ref, "status": p.status, "amount_paise": p.amount_paise, "short_url": p.short_url,
                      "refunded_paise": p.refunded_paise} for p in payments or []],
    }


def _payments(db: Session, o: Order) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.order_id == o.id).order_by(Payment.id)))


class OrderIn(BaseModel):
    phone: str
    name: str = Field("", max_length=120)
    order_type: str = "pickup"
    special_instructions: str = Field("", max_length=1000)


class LineIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(1, ge=1, le=50)
    variant_id: int | None = None
    addon_ids: list[int] = []
    instructions: str = Field("", max_length=300)


class LinePatch(BaseModel):
    quantity: int | None = Field(None, ge=0, le=50)
    variant_id: int | None = None
    addon_ids: list[int] | None = None
    instructions: str | None = Field(None, max_length=300)


class ConfirmIn(BaseModel):
    scheduled_for: str | None = None
    customer_gstin: str = Field("", max_length=15)


class StatusIn(BaseModel):
    status: str
    reason: str = Field("", max_length=200)
    eta_minutes: int | None = Field(None, ge=0, le=1440)


@router.get("")
def list_orders(day: date | None = None, status: str | None = None, q: str | None = None,
                db: Session = Depends(get_db), _: StaffUser = Depends(require("orders.view"))):
    stmt = select(Order).join(Customer).order_by(Order.created_at.desc())
    if day:
        start, end = day_bounds(get_restaurant(db), day)
        stmt = stmt.where(Order.created_at >= start, Order.created_at < end)
    if status:
        stmt = stmt.where(Order.status.in_(status.split(",")))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Order.ref.ilike(like), Customer.name.ilike(like), Customer.phone.ilike(like)))
    return [order_out(o) for o in db.scalars(stmt.limit(300))]


@router.get("/{ref}")
def read_order(ref: str, db: Session = Depends(get_db), _: StaffUser = Depends(require("orders.view"))):
    o = service.get_order(db, ref)
    return order_out(o, _payments(db, o)) | {"quote": service.kitchen_quote(db, o)}


@router.post("")
def create_order(body: OrderIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.manage"))):
    customer = get_or_create(db, body.phone, body.name)
    o = service.create_draft(db, customer=customer, channel="dashboard", actor=actor(user), order_type=body.order_type)
    o.special_instructions = body.special_instructions
    db.commit()
    return order_out(o)


@router.post("/{ref}/items")
def add_line(ref: str, body: LineIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.manage"))):
    o = service.get_order(db, ref, for_update=True)
    service.add_item(db, o, item_id=body.menu_item_id, quantity=body.quantity, variant_id=body.variant_id,
                     addon_ids=body.addon_ids, instructions=body.instructions, actor=actor(user))
    db.commit()
    return order_out(o)


@router.patch("/{ref}/items/{line_id}")
def edit_line(ref: str, line_id: int, body: LinePatch, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.manage"))):
    o = service.get_order(db, ref, for_update=True)
    service.update_item(db, o, line_id, actor=actor(user), quantity=body.quantity, variant_id=body.variant_id,
                        addon_ids=body.addon_ids, instructions=body.instructions)
    db.commit()
    return order_out(o)


@router.delete("/{ref}/items/{line_id}")
def delete_line(ref: str, line_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.manage"))):
    o = service.get_order(db, ref, for_update=True)
    service.remove_item(db, o, line_id, actor=actor(user))
    db.commit()
    return order_out(o)


@router.post("/{ref}/confirm")
def confirm_order(ref: str, body: ConfirmIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.manage"))):
    o = service.get_order(db, ref, for_update=True)
    when = parse_time(get_restaurant(db), body.scheduled_for) if body.scheduled_for else None
    service.confirm(db, o, actor=actor(user), scheduled_for=when, gstin=body.customer_gstin)
    db.commit()
    return order_out(o, _payments(db, o))


@router.post("/{ref}/reopen")
def reopen(ref: str, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.manage"))):
    o = service.get_order(db, ref, for_update=True)
    service.reopen_for_edit(db, o, actor=actor(user))
    db.commit()
    return order_out(o)


KITCHEN_STEPS = {"accepted", "preparing", "ready", "completed"}


@router.post("/{ref}/status")
def set_status(ref: str, body: StatusIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("orders.kitchen"))):
    if body.status not in KITCHEN_STEPS and not can(user.role, "orders.manage"):
        raise DomainError("You don't have permission to do that.", "forbidden", 403)
    if body.status not in KITCHEN_STEPS | {"cancelled"}:
        raise DomainError("Staff can accept, prepare, mark ready, complete or cancel orders.")
    o = service.get_order(db, ref, for_update=True)
    service.transition(db, o, body.status, actor=actor(user), reason=body.reason or ("rejected by restaurant" if body.status == "cancelled" else ""),
                       eta_minutes=body.eta_minutes)
    db.commit()
    return order_out(o, _payments(db, o))


@router.get("/{ref}/invoice")
def invoice(ref: str, db: Session = Depends(get_db), _: StaffUser = Depends(require("orders.view"))):
    """GST-ready invoice data (rendered/printed by the dashboard)."""
    o = service.get_order(db, ref)
    if not o.invoice_number:
        raise DomainError("An invoice is issued once the order is submitted to the kitchen.")
    r = get_restaurant(db)
    return {
        "invoice_number": o.invoice_number, "date": o.submitted_at or o.created_at, "order_ref": o.ref,
        "seller": {"name": r.legal_name or r.name, "trade_name": r.name, "address": r.address, "city": r.city,
                   "state": r.state, "state_code": r.state_code, "pincode": r.pincode, "gstin": r.gstin,
                   "fssai": r.fssai_license, "phone": r.phone},
        "buyer": {"name": o.customer.name, "phone": o.customer.phone, "gstin": o.customer_gstin},
        "place_of_supply": r.state_code, "sac": "996331",
        "bill": o.bill, "amount_paid_paise": o.amount_paid_paise,
    }
