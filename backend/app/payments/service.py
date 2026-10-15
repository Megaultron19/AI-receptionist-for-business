"""Payment links, verified payment state, refunds and reconciliation.

Rules:
- Amounts come only from server-computed orders/reservations.
- 'paid' is set only by sync_link(), which fetches the link from Razorpay and checks it is paid in full.
  Webhooks merely tell us *when* to look; duplicates and out-of-order events are therefore harmless.
- Every external call happens in a job with bounded retries; Razorpay's reference_id / refund receipt
  are our idempotency keys, so a retried job finds the link/refund it already created instead of
  creating another.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..core.errors import DomainError
from ..core.events import alert, audit, usage
from ..core.jobs import enqueue
from ..core.models import WebhookEvent
from ..db import utcnow
from ..orders import service as orders
from ..orders.billing import rupees
from ..orders.models import Order
from ..reservations import engine as reservations
from ..reservations.engine import new_ref
from ..reservations.models import Reservation
from ..restaurant.service import get_restaurant
from ..notifications.service import can_whatsapp
from . import razorpay
from .models import Payment, Refund

log = logging.getLogger(__name__)
ORDER_LINK_TTL = timedelta(minutes=30)
MIN_LINK_TTL = timedelta(minutes=16)
OPEN = ("creating", "created", "pending")
SETTLED = ("paid", "refunded", "partially_refunded")


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _ensure_link(db: Session, p: Payment, *, description: str, customer) -> Payment:
    """Create the Razorpay link for a 'creating' payment, or adopt one a previous attempt already made."""
    db.commit()
    link = razorpay.find_payment_link(p.ref)
    if not link:
        link = razorpay.create_payment_link(amount_paise=p.amount_paise, reference_id=p.ref, description=description,
                                            customer_name=customer.name, contact=customer.phone, expire_by=_ts(p.expires_at),
                                            notes={"payment_ref": p.ref, "purpose": p.purpose},
                                            sms=not can_whatsapp(db, customer, "payment_link"))
    if link.get("amount") != p.amount_paise:
        raise razorpay.RazorpayError(f"link {link.get('id')} amount {link.get('amount')} != expected {p.amount_paise}")
    p.provider_link_id, p.short_url, p.status = link["id"], link.get("short_url", ""), "created"
    audit(db, "payment.link_created", "payment", p.ref, amount=p.amount_paise, purpose=p.purpose)
    return p


def create_order_link(db: Session, order_id: int) -> Payment | None:
    o = db.get(Order, order_id, with_for_update=True)
    if not o or o.status != "awaiting_payment" or o.amount_due_paise <= 0:
        return None
    p = db.scalar(select(Payment).where(Payment.order_id == o.id, Payment.status.in_(OPEN),
                                        Payment.amount_paise == o.amount_due_paise))
    if p and p.status != "creating":
        return p
    if not p:
        p = Payment(ref=new_ref("P") + "O", purpose="order", order_id=o.id, amount_paise=o.amount_due_paise,
                    expires_at=utcnow() + ORDER_LINK_TTL)
        db.add(p)
        db.flush()
    r = get_restaurant(db)
    part = "" if o.amount_due_paise == o.total_paise else f" (advance of {rupees(o.amount_due_paise)} on {rupees(o.total_paise)})"
    _ensure_link(db, p, description=f"{r.name} order {o.ref}{part}", customer=o.customer)
    enqueue(db, "notify.payment_link", {"payment_id": p.id}, dedupe_key=f"notify:paylink:{p.id}")
    return p


def create_deposit_link(db: Session, reservation_id: int) -> Payment | None:
    res = db.get(Reservation, reservation_id, with_for_update=True)
    if not res or res.status != "held" or res.hold_reason != "deposit" or res.deposit_paise <= 0:
        return None
    p = db.scalar(select(Payment).where(Payment.reservation_id == res.id, Payment.status.in_(OPEN)))
    if p and p.status != "creating":
        return p
    if not p:
        expires = max(res.hold_expires_at, utcnow() + MIN_LINK_TTL)
        if expires > res.hold_expires_at:
            res.hold_expires_at = expires
            enqueue(db, "reservation.hold_expire", {"id": res.id}, run_at=expires, dedupe_key=f"hold:res:{res.id}:{_ts(expires)}")
        p = Payment(ref=new_ref("P") + "D", purpose="deposit", reservation_id=res.id, amount_paise=res.deposit_paise,
                    expires_at=expires)
        db.add(p)
        db.flush()
    r = get_restaurant(db)
    _ensure_link(db, p, description=f"{r.name} table deposit, booking {res.ref}", customer=res.customer)
    enqueue(db, "notify.payment_link", {"payment_id": p.id}, dedupe_key=f"notify:paylink:{p.id}")
    return p


def sync_link(db: Session, p: Payment) -> Payment:
    """Fetch the link from Razorpay (the independent verification) and apply its state."""
    if not p.provider_link_id:
        return p
    link = razorpay.fetch_payment_link(p.provider_link_id)
    p.last_synced_at = utcnow()
    status = link.get("status")
    if status == "paid":
        if link.get("amount_paid", 0) < p.amount_paise or link.get("amount") != p.amount_paise:
            alert(db, "payment_mismatch", f"Payment {p.ref}: Razorpay reports {link.get('amount_paid')} paid, expected {p.amount_paise}.",
                  severity="error", ref=("payment", p.ref))
            return p
        captured = [x for x in link.get("payments") or [] if x.get("status") == "captured"]
        mark_paid(db, p, captured[-1]["payment_id"] if captured else p.provider_payment_id)
    elif status in ("expired", "cancelled") and p.status in OPEN:
        p.status = status
        audit(db, f"payment.{status}", "payment", p.ref, actor=("provider", "razorpay"))
        _payment_closed_unpaid(db, p)
    return p


def mark_paid(db: Session, p: Payment, provider_payment_id: str | None) -> None:
    if p.status in SETTLED:
        return
    p.status, p.paid_at = "paid", utcnow()
    p.provider_payment_id = provider_payment_id or p.provider_payment_id
    audit(db, "payment.paid", "payment", p.ref, actor=("provider", "razorpay"), amount=p.amount_paise,
          provider_payment_id=p.provider_payment_id)
    usage(db, "payment_paid", 1, purpose=p.purpose, amount_paise=p.amount_paise)
    enqueue(db, "notify.payment_received", {"payment_id": p.id}, dedupe_key=f"notify:paid:{p.id}")
    if p.order_id:
        o = db.get(Order, p.order_id, with_for_update=True)
        o.amount_paid_paise += p.amount_paise
        if o.status in ("awaiting_payment", "payment_pending") and p.amount_paise >= o.amount_due_paise:
            orders.transition(db, o, "paid", actor=("provider", "razorpay"))
            orders.transition(db, o, "submitted", actor=("system", None))
        else:
            alert(db, "late_payment", f"Payment {p.ref} arrived for order {o.ref} which is {o.status}; refunding it.",
                  severity="warning", ref=("order", o.ref))
            initiate_refund(db, p, p.amount_paise, "payment for an outdated order", ("system", None))
    if p.reservation_id:
        res = db.get(Reservation, p.reservation_id, with_for_update=True)
        if res.status == "held":
            reservations.transition(db, res, "confirmed", actor=("provider", "razorpay"))
        else:
            alert(db, "late_payment", f"Deposit {p.ref} paid for booking {res.ref} which is {res.status}; refunding it.",
                  severity="warning", ref=("reservation", res.ref))
            initiate_refund(db, p, p.amount_paise, "deposit for an expired booking", ("system", None))


def _payment_closed_unpaid(db: Session, p: Payment) -> None:
    if p.order_id:
        o = db.get(Order, p.order_id, with_for_update=True)
        if o.status in ("awaiting_payment", "payment_pending"):
            orders.transition(db, o, "cancelled", actor=("system", None), reason="payment link expired")


def record_failure(db: Session, p: Payment, reason: str) -> None:
    """A payment attempt failed; the link stays usable until it expires, so the order keeps waiting."""
    if p.status in SETTLED:
        return
    p.last_failure = reason[:300]
    if p.status == "pending":
        p.status = "created"
        if p.order_id:
            o = db.get(Order, p.order_id, with_for_update=True)
            if o.status == "payment_pending":
                orders.transition(db, o, "awaiting_payment", actor=("provider", "razorpay"), reason=reason)
    audit(db, "payment.failed_attempt", "payment", p.ref, actor=("provider", "razorpay"), reason=reason[:300])


def record_authorized(db: Session, p: Payment) -> None:
    if p.status == "created":
        p.status = "pending"
        if p.order_id:
            o = db.get(Order, p.order_id, with_for_update=True)
            if o.status == "awaiting_payment":
                orders.transition(db, o, "payment_pending", actor=("provider", "razorpay"))


def cancel_open_links(db: Session, order_id: int) -> None:
    for p in db.scalars(select(Payment).where(Payment.order_id == order_id, Payment.status.in_(OPEN))):
        if p.provider_link_id:
            try:
                razorpay.cancel_payment_link(p.provider_link_id)
            except razorpay.RazorpayError:
                sync_link(db, p)
                if p.status in SETTLED:
                    continue
                raise
        p.status = "cancelled"
        audit(db, "payment.cancelled", "payment", p.ref)



def refundable(p: Payment) -> int:
    pending = sum(r.amount_paise for r in p.refunds if r.status in ("requested", "pending"))
    return p.amount_paise - p.refunded_paise - pending if p.status in SETTLED else 0


def initiate_refund(db: Session, p: Payment, amount: int, reason: str, actor: tuple[str, object]) -> Refund:
    if amount <= 0 or amount > refundable(p):
        raise DomainError(f"Refundable amount is {rupees(refundable(p))}.")
    rf = Refund(ref=new_ref("RF"), payment_id=p.id, amount_paise=amount, reason=reason[:200], created_by=f"{actor[0]}:{actor[1]}")
    db.add(rf)
    db.flush()
    db.refresh(p)
    audit(db, "refund.requested", "payment", p.ref, actor=actor, amount=amount, refund=rf.ref, reason=reason)
    enqueue(db, "payments.refund", {"refund_id": rf.id}, dedupe_key=f"refund:{rf.id}")
    return rf


def execute_refund(db: Session, refund_id: int) -> None:
    rf = db.get(Refund, refund_id, with_for_update=True)
    if not rf or rf.status != "requested":
        return
    p = db.get(Payment, rf.payment_id)
    if not p.provider_payment_id:
        sync_link(db, p)
        if not p.provider_payment_id:
            raise razorpay.RazorpayError(f"payment {p.ref} has no Razorpay payment id yet")
    existing = next((x for x in razorpay.list_refunds(p.provider_payment_id) if x.get("receipt") == rf.ref), None)
    data = existing or razorpay.create_refund(p.provider_payment_id, rf.amount_paise, rf.ref, {"refund_ref": rf.ref, "reason": rf.reason[:200]})
    rf.provider_refund_id = data["id"]
    apply_refund_status(db, rf, data.get("status", "pending"))


def apply_refund_status(db: Session, rf: Refund, status: str) -> None:
    status = {"processed": "processed", "failed": "failed"}.get(status, "pending")
    if rf.status == status or rf.status in ("processed", "failed"):
        return
    rf.status = status
    p = db.get(Payment, rf.payment_id, with_for_update=True)
    audit(db, f"refund.{status}", "payment", p.ref, actor=("provider", "razorpay"), refund=rf.ref, amount=rf.amount_paise)
    if status == "failed":
        alert(db, "refund_failed", f"Refund {rf.ref} of {rupees(rf.amount_paise)} for payment {p.ref} failed. Check Razorpay.",
              severity="error", ref=("payment", p.ref))
        return
    if status == "processed":
        p.refunded_paise += rf.amount_paise
        p.status = "refunded" if p.refunded_paise >= p.amount_paise else "partially_refunded"
        usage(db, "payment_refunded", 1, amount_paise=rf.amount_paise)
        if p.order_id:
            o = db.get(Order, p.order_id, with_for_update=True)
            paid = sum(x.amount_paise - x.refunded_paise for x in db.scalars(select(Payment).where(Payment.order_id == o.id, Payment.status.in_(SETTLED))))
            if paid <= 0 and o.status in ("cancelled", "completed"):
                orders.transition(db, o, "refunded", actor=("provider", "razorpay"))
        enqueue(db, "notify.refund", {"refund_id": rf.id}, dedupe_key=f"notify:refund:{rf.id}")


def refund_order(db: Session, order_id: int, reason: str) -> None:
    for p in db.scalars(select(Payment).where(Payment.order_id == order_id, Payment.status.in_(SETTLED))):
        if (amount := refundable(p)) > 0:
            initiate_refund(db, p, amount, reason, ("system", None))



def store_webhook(db: Session, raw: bytes, event_id: str | None) -> bool:
    """Persist a verified webhook and queue its processing. Returns False for duplicates."""
    event = json.loads(raw)
    eid = event_id or hashlib.sha256(raw).hexdigest()
    row = db.execute(insert(WebhookEvent).values(provider="razorpay", event_id=eid, event_type=event.get("event", "?")[:64],
                                                 payload=event, status="received", received_at=utcnow())
                     .on_conflict_do_nothing(constraint="uq_webhook_provider_event").returning(WebhookEvent.id)).scalar()
    if row is None:
        return False
    usage(db, "webhook_razorpay", event=event.get("event"))
    enqueue(db, "payments.process_webhook", {"webhook_id": row}, dedupe_key=f"webhook:razorpay:{row}")
    return True


def _find_payment(db: Session, *, link_id: str | None = None, payment_ref: str | None = None, provider_payment_id: str | None = None) -> Payment | None:
    for col, val in ((Payment.provider_link_id, link_id), (Payment.ref, payment_ref), (Payment.provider_payment_id, provider_payment_id)):
        if val and (p := db.scalar(select(Payment).where(col == val).with_for_update())):
            return p
    return None


def process_webhook(db: Session, webhook_id: int) -> None:
    ev = db.get(WebhookEvent, webhook_id, with_for_update=True)
    if not ev or ev.status in ("processed", "ignored"):
        return
    kind, payload = ev.event_type, ev.payload.get("payload", {})
    status = "processed"
    if kind.startswith("payment_link."):
        p = _find_payment(db, link_id=payload.get("payment_link", {}).get("entity", {}).get("id"))
        if p:
            sync_link(db, p)
        else:
            status = "ignored"
    elif kind.startswith("payment."):
        ent = payload.get("payment", {}).get("entity", {})
        p = _find_payment(db, payment_ref=(ent.get("notes") or {}).get("payment_ref"), provider_payment_id=ent.get("id"))
        if not p:
            status = "ignored"
        elif kind == "payment.failed":
            record_failure(db, p, ent.get("error_description") or ent.get("error_reason") or "payment failed")
        elif kind == "payment.authorized":
            record_authorized(db, p)
        elif kind == "payment.captured":
            p.provider_payment_id = p.provider_payment_id or ent.get("id")
            sync_link(db, p)
    elif kind.startswith("refund."):
        ent = payload.get("refund", {}).get("entity", {})
        rf = db.scalar(select(Refund).where(Refund.provider_refund_id == ent.get("id"))) or \
            db.scalar(select(Refund).where(Refund.ref == (ent.get("receipt") or "")))
        if rf:
            rf.provider_refund_id = rf.provider_refund_id or ent.get("id")
            apply_refund_status(db, rf, ent.get("status") or kind.split(".")[1])
        else:
            status = "ignored"
    else:
        status = "ignored"
    ev.status, ev.processed_at = status, utcnow()


def reconcile(db: Session) -> int:
    """Catch anything a lost webhook missed: re-check open links and pending refunds with Razorpay."""
    n = 0
    cutoff = utcnow() - timedelta(minutes=2)
    for p in db.scalars(select(Payment).where(Payment.status.in_(("created", "pending")), Payment.created_at < cutoff,
                                              (Payment.last_synced_at.is_(None)) | (Payment.last_synced_at < cutoff))).all():
        sync_link(db, p)
        n += 1
    for rf in db.scalars(select(Refund).where(Refund.status == "pending", Refund.provider_refund_id.is_not(None),
                                             Refund.updated_at < utcnow() - timedelta(minutes=10))).all():
        p = db.get(Payment, rf.payment_id)
        match = next((x for x in razorpay.list_refunds(p.provider_payment_id) if x.get("id") == rf.provider_refund_id), None)
        if match:
            apply_refund_status(db, rf, match.get("status", "pending"))
        n += 1
    return n
