"""Customer notifications over WhatsApp, respecting Meta's rules:
- inside the 24h customer-service window (customer messaged us recently): free-form text/images;
- outside it: only an approved template, and only if the customer opted in;
- otherwise the message is skipped and staff are alerted so they can call instead.
Each logical notification is a ledger row keyed by dedupe_key, so job retries never double-send."""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..conversations.models import Message, Notification
from ..core.events import alert, usage
from ..customers.models import Customer
from ..customers.service import in_service_window
from ..db import utcnow
from ..restaurant.service import get_restaurant, tz
from ..whatsapp import client as wa

log = logging.getLogger(__name__)
DONE = ("sent", "delivered", "read", "skipped")


def fmt_time(dt: datetime, db: Session) -> str:
    return dt.astimezone(tz(get_restaurant(db))).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def can_whatsapp(db: Session, customer: Customer, kind: str) -> bool:
    """Whether a notification of this kind would actually be delivered on WhatsApp right now."""
    if customer.anonymized_at or customer.whatsapp_unavailable or not wa.configured():
        return False
    return in_service_window(customer) or (customer.whatsapp_opt_in and bool((get_restaurant(db).whatsapp_templates or {}).get(kind)))


def send(db: Session, customer: Customer, *, kind: str, dedupe_key: str, text: str, template_params: list[str],
         ref: tuple[str, str] = ("", ""), qr_png: bytes | None = None) -> Notification:
    db.execute(insert(Notification).values(dedupe_key=dedupe_key, kind=kind, customer_id=customer.id, channel="whatsapp",
                                           status="pending", ref_type=ref[0], ref_id=str(ref[1]), created_at=utcnow(),
                                           method="", error="")
               .on_conflict_do_nothing(index_elements=["dedupe_key"]))
    n = db.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key).with_for_update())
    if n.status in DONE:
        return n
    r = get_restaurant(db)
    template = (r.whatsapp_templates or {}).get(kind)
    if customer.anonymized_at or customer.whatsapp_unavailable:
        return _skip(db, n, customer, "customer has no WhatsApp", text)
    if not wa.configured():
        return _skip(db, n, customer, "WhatsApp is not configured", text)
    if in_service_window(customer):
        method = "session"
    elif customer.whatsapp_opt_in and template:
        method = "template"
    else:
        why = "no WhatsApp consent" if not customer.whatsapp_opt_in else f"no approved '{kind}' template configured"
        return _skip(db, n, customer, why, text)
    db.commit()
    try:
        if method == "session" and qr_png:
            msg_id = wa.send_image(customer.phone, wa.upload_png(qr_png), text)
        elif method == "session":
            msg_id = wa.send_text(customer.phone, text)
        else:
            msg_id = wa.send_template(customer.phone, template["name"], template.get("language", "en"), template_params)
    except wa.WhatsAppError as e:
        if e.retryable:
            raise
        if e.code in wa.NOT_ON_WHATSAPP:
            customer.whatsapp_unavailable = True
        n.status, n.error = "failed", str(e)[:300]
        db.add(Message(customer_id=customer.id, direction="out", sender="system", body=text, status="failed", error=str(e)[:300],
                       template=template["name"] if method == "template" else ""))
        alert(db, "notification_failed", f"Couldn't send {kind.replace('_', ' ')} to {customer.name or customer.phone}: {e}. "
              "Please contact the customer another way.", severity="warning", ref=(ref[0] or "customer", ref[1] or customer.id))
        return n
    n.status, n.method, n.wa_message_id, n.sent_at = "sent", method, msg_id, utcnow()
    db.commit()
    db.add(Message(customer_id=customer.id, direction="out", sender="system", body=text, wa_message_id=msg_id, status="sent",
                   template=template["name"] if method == "template" else "", media="image" if qr_png and method == "session" else ""))
    s = get_settings()
    usage(db, "whatsapp_out", 1, s.cost_whatsapp_template_msg_paise if method == "template" else s.cost_whatsapp_service_msg_paise,
          kind=kind, method=method)
    return n


def _skip(db: Session, n: Notification, customer: Customer, why: str, text: str) -> Notification:
    n.status, n.error = "skipped", why
    if n.kind not in ("booking_reminder",):
        alert(db, "notification_skipped", f"{n.kind.replace('_', ' ').capitalize()} for {customer.name or customer.phone} "
              f"was not sent on WhatsApp ({why}). Message: {text[:300]}", severity="warning",
              ref=(n.ref_type or "customer", n.ref_id or customer.id))
    return n


def send_staff(db: Session, message: str, dedupe_key: str) -> None:
    """Alert restaurant staff on WhatsApp (needs an approved 'staff_alert' template outside the 24h window)."""
    r = get_restaurant(db)
    template = (r.whatsapp_templates or {}).get("staff_alert")
    if not r.staff_alert_numbers or not wa.configured():
        return
    for number in r.staff_alert_numbers:
        key = f"{dedupe_key}:{number}"
        db.execute(insert(Notification).values(dedupe_key=key, kind="staff_alert", customer_id=_staff_customer(db, number),
                                               status="pending", created_at=utcnow(), method="", error="", channel="whatsapp",
                                               ref_type="", ref_id="")
                   .on_conflict_do_nothing(index_elements=["dedupe_key"]))
        n = db.scalar(select(Notification).where(Notification.dedupe_key == key).with_for_update())
        if n.status in DONE:
            continue
        try:
            n.wa_message_id = (wa.send_template(number, template["name"], template.get("language", "en"), [message[:900]])
                               if template else wa.send_text(number, message))
            n.status, n.sent_at = "sent", utcnow()
        except wa.WhatsAppError as e:
            if e.retryable:
                raise
            n.status, n.error = "failed", str(e)[:300]


def _staff_customer(db: Session, number: str) -> int:
    from ..customers.service import get_or_create
    return get_or_create(db, number, "Staff").id
