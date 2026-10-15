from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..core.errors import DomainError, NotFound
from ..db import get_db
from ..deps import actor, require
from ..orders.models import Order
from ..reservations.models import Reservation
from . import razorpay, service
from .models import Payment

router = APIRouter(tags=["payments"])


def payment_out(p: Payment, db: Session) -> dict:
    o = db.get(Order, p.order_id) if p.order_id else None
    res = db.get(Reservation, p.reservation_id) if p.reservation_id else None
    return {"id": p.id, "ref": p.ref, "purpose": p.purpose, "status": p.status, "amount_paise": p.amount_paise,
            "refunded_paise": p.refunded_paise, "refundable_paise": service.refundable(p), "short_url": p.short_url,
            "provider_link_id": p.provider_link_id, "provider_payment_id": p.provider_payment_id,
            "created_at": p.created_at, "paid_at": p.paid_at, "expires_at": p.expires_at, "last_failure": p.last_failure,
            "order_ref": o.ref if o else None, "reservation_ref": res.ref if res else None,
            "refunds": [{"ref": r.ref, "amount_paise": r.amount_paise, "status": r.status, "reason": r.reason,
                         "created_at": r.created_at} for r in p.refunds]}


class RefundIn(BaseModel):
    amount_paise: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=200)


@router.get("/api/payments")
def list_payments(status: str | None = None, db: Session = Depends(get_db), _: StaffUser = Depends(require("payments.view"))):
    stmt = select(Payment).order_by(Payment.created_at.desc()).limit(300)
    if status:
        stmt = stmt.where(Payment.status.in_(status.split(",")))
    return [payment_out(p, db) for p in db.scalars(stmt)]


@router.post("/api/payments/{ref}/refund")
def refund(ref: str, body: RefundIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("payments.refund"))):
    p = db.scalar(select(Payment).where(Payment.ref == ref).with_for_update())
    if not p:
        raise NotFound("Payment")
    service.initiate_refund(db, p, body.amount_paise, body.reason, actor(user))
    db.commit()
    return payment_out(p, db)


@router.post("/api/payments/{ref}/sync")
def sync(ref: str, db: Session = Depends(get_db), _: StaffUser = Depends(require("payments.view"))):
    p = db.scalar(select(Payment).where(Payment.ref == ref).with_for_update())
    if not p:
        raise NotFound("Payment")
    try:
        service.sync_link(db, p)
    except razorpay.RazorpayError as e:
        raise DomainError(f"Couldn't reach Razorpay: {e}", "provider_error", 502)
    db.commit()
    return payment_out(p, db)


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()  # signature is over the exact raw bytes
    if not razorpay.verify_webhook(raw, request.headers.get("X-Razorpay-Signature", "")):
        raise DomainError("Invalid signature", "bad_signature", 400)
    stored = service.store_webhook(db, raw, request.headers.get("X-Razorpay-Event-Id"))
    db.commit()
    return {"ok": True, "duplicate": not stored}
