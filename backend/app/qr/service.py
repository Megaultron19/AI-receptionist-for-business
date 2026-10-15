import hashlib
import io
import re
import secrets
from datetime import timedelta

import segno
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.events import audit
from ..db import utcnow
from ..orders import service as orders
from ..orders.models import Order
from ..reservations import engine as reservations
from ..reservations.models import Reservation
from .models import QrScan, QrToken

TOKEN_RE = re.compile(r"([A-Za-z0-9_-]{32,64})$")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db: Session, *, reservation: Reservation | None = None, order: Order | None = None) -> str:
    """New token for a booking/order; any older token for the same record is revoked."""
    token = secrets.token_urlsafe(32)
    if reservation:
        db.execute(update(QrToken).where(QrToken.reservation_id == reservation.id, QrToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
        expires = reservation.ends_at + timedelta(hours=3)
    else:
        db.execute(update(QrToken).where(QrToken.order_id == order.id, QrToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
        expires = max(order.scheduled_for or utcnow(), utcnow()) + timedelta(hours=12)
    db.add(QrToken(token_hash=_hash(token), kind="reservation" if reservation else "order",
                   reservation_id=reservation.id if reservation else None, order_id=order.id if order else None, expires_at=expires))
    db.flush()
    return token


def url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/q/{token}"


def png(token: str, scale: int = 8) -> bytes:
    buf = io.BytesIO()
    segno.make(url(token), error="m").save(buf, kind="png", scale=scale, border=3)
    return buf.getvalue()


def extract_token(scanned: str) -> str:
    """Accept the raw token or the full URL the camera read."""
    m = TOKEN_RE.search(scanned.strip().rstrip("/"))
    return m.group(1) if m else ""


def _find(db: Session, token: str) -> QrToken | None:
    return db.scalar(select(QrToken).where(QrToken.token_hash == _hash(token)).with_for_update()) if token else None


def describe(db: Session, scanned: str, *, staff_id: int | None, action: str = "lookup") -> dict:
    """What staff see after scanning. Never changes state unless action == 'checkin'."""
    qr = _find(db, extract_token(scanned))
    if not qr:
        db.add(QrScan(qr_id=None, staff_id=staff_id, action=action, result="invalid"))
        return {"result": "invalid", "message": "This QR code is not valid for this restaurant."}
    qr.scan_count += 1
    first = qr.first_scanned_at
    qr.first_scanned_at = qr.first_scanned_at or utcnow()

    def done(result: str, message: str, **extra) -> dict:
        db.add(QrScan(qr_id=qr.id, staff_id=staff_id, action=action, result=result))
        audit(db, f"qr.{action}", qr.kind, (extra.get("ref")), actor=("staff", staff_id), result=result, scan=qr.scan_count)
        return {"result": result, "message": message, "kind": qr.kind, "scan_count": qr.scan_count,
                "first_scanned_at": first, **extra}

    if qr.revoked_at:
        return done("revoked", "This QR code was replaced by a newer one. Ask the guest for the latest confirmation.")
    if qr.expires_at < utcnow():
        return done("expired", "This QR code has expired.")

    if qr.kind == "reservation":
        res = db.get(Reservation, qr.reservation_id, with_for_update=True)
        info = {"ref": res.ref, "status": res.status, "party_size": res.party_size, "starts_at": res.starts_at,
                "name": res.customer.name, "table_ids": sorted({a.table_id for a in res.allocations if a.active}),
                "notes": res.notes}
        if res.status in ("arrived", "seated", "completed"):
            when = (res.arrived_at or res.seated_at).isoformat(timespec="minutes") if (res.arrived_at or res.seated_at) else ""
            return done("already_checked_in", f"Already checked in{(' at ' + when) if when else ''}.", **info)
        if res.status == "held":
            return done("not_confirmed", "This booking is not confirmed yet (deposit or offer pending).", **info)
        if res.status == "cancelled":
            return done("cancelled", "This booking was cancelled.", **info)
        if action == "checkin":
            reservations.transition(db, res, "arrived", actor=("staff", staff_id))
            info["status"] = res.status
            return done("checked_in", f"Checked in: {res.customer.name or 'guest'}, party of {res.party_size}.", **info)
        return done("valid", "Valid booking. Check the guest in?", **info)

    o = db.get(Order, qr.order_id, with_for_update=True)
    paid_ok = o.amount_paid_paise >= o.amount_due_paise
    info = {"ref": o.ref, "status": o.status, "name": o.customer.name, "total_paise": o.total_paise,
            "amount_paid_paise": o.amount_paid_paise, "balance_due_paise": max(o.total_paise - o.amount_paid_paise, 0),
            "payment_verified": paid_ok, "items": [f"{l.quantity} x {l.item_name}" + (f" ({l.variant_name})" if l.variant_name else "")
                                                   for l in o.items]}
    if o.status == "completed":
        return done("already_collected", "This order was already handed over.", **info)
    if o.status in ("cancelled", "refunded"):
        return done("cancelled", "This order was cancelled.", **info)
    if not paid_ok:
        return done("unpaid", "Payment for this order has not been verified.", **info)
    if o.status != "ready":
        return done("not_ready", f"Order is {o.status.replace('_', ' ')}; not ready for pickup yet.", **info)
    if action == "checkin":
        orders.transition(db, o, "completed", actor=("staff", staff_id))
        info["status"] = o.status
        return done("handed_over", "Order handed over.", **info)
    return done("valid", "Ready for pickup. Hand over?", **info)


def public_view(db: Session, token: str) -> dict | None:
    """What anyone holding the link may see: no names or phone numbers."""
    qr = db.scalar(select(QrToken).where(QrToken.token_hash == _hash(token)))
    if not qr or qr.revoked_at or qr.expires_at < utcnow():
        return None
    if qr.kind == "reservation":
        res = db.get(Reservation, qr.reservation_id)
        return {"kind": "reservation", "ref": res.ref, "status": res.status, "party_size": res.party_size, "starts_at": res.starts_at}
    o = db.get(Order, qr.order_id)
    return {"kind": "order", "ref": o.ref, "status": o.status, "estimated_ready_at": o.estimated_ready_at}
