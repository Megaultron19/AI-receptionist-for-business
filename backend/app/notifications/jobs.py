"""Job handlers that compose and send customer messages. Each re-reads current state first, so a stale
job (booking since cancelled, order since edited) sends nothing."""
from sqlalchemy.orm import Session

from ..core.jobs import handler
from ..orders.billing import rupees
from ..orders.models import Order
from ..payments.models import Payment, Refund
from ..qr import service as qr
from ..reservations.models import Reservation
from ..restaurant.service import get_restaurant
from .service import fmt_time, send, send_staff


def _tables(db: Session, res: Reservation) -> str:
    from ..tables.models import DiningTable
    codes = [db.get(DiningTable, a.table_id).code for a in res.allocations if a.active]
    return f"Table {', '.join(codes)}" if codes else "Table assigned on arrival"


@handler("notify.reservation")
def notify_reservation(db: Session, p: dict) -> None:
    res = db.get(Reservation, p["id"])
    if not res:
        return
    r, c, event = get_restaurant(db), res.customer, p["event"]
    when = fmt_time(res.starts_at, db)
    name = c.name or "there"
    key = f"res:{res.id}:{event}:{int(res.starts_at.timestamp())}"
    if event in ("confirmed", "rescheduled"):
        if res.status != "confirmed":
            return
        token = qr.issue(db, reservation=res)
        lines = [f"{'Booking updated' if event == 'rescheduled' else 'Your table is booked'} at {r.name}! ✅",
                 f"Ref: {res.ref}", f"When: {when}", f"Guests: {res.party_size}", _tables(db, res)]
        if r.address:
            lines.append(f"Address: {r.address}" + (f" ({r.maps_url})" if r.maps_url else ""))
        if r.arrival_instructions:
            lines.append(r.arrival_instructions)
        lines += ["Show this QR code when you arrive.", f"Can't open the image? {qr.url(token)}"]
        send(db, c, kind="booking_confirmation", dedupe_key=key, text="\n".join(lines), qr_png=qr.png(token),
             template_params=[name, r.name, res.ref, when, str(res.party_size), qr.url(token)], ref=("reservation", res.ref))
    elif event == "cancelled":
        if res.status != "cancelled":
            return
        send(db, c, kind="cancellation", dedupe_key=key,
             text=f"Your booking {res.ref} at {r.name} for {when} has been cancelled." +
                  (f" Reason: {res.cancel_reason}." if res.cancel_reason and "customer" not in res.cancel_reason else "") +
                  " We hope to see you another time.",
             template_params=[name, r.name, res.ref, when], ref=("reservation", res.ref))
    elif event == "waitlist_offer":
        if res.status != "held":
            return
        mins = max(int((res.hold_expires_at - res.created_at).total_seconds() // 60), 1)
        send(db, c, kind="waitlist_offer", dedupe_key=key,
             text=f"Good news from {r.name}! A table for {res.party_size} is free at {when}. "
                  f"Reply YES within {mins} minutes to confirm (ref {res.ref}), or NO to pass.",
             template_params=[name, r.name, when, str(res.party_size), str(mins)], ref=("reservation", res.ref))


@handler("reservation.reminder")
def reminder(db: Session, p: dict) -> None:
    res = db.get(Reservation, p["id"])
    if not res or res.status != "confirmed" or int(res.starts_at.timestamp()) != p["starts_at"]:
        return  # cancelled or moved since this reminder was scheduled
    r, c = get_restaurant(db), res.customer
    when = fmt_time(res.starts_at, db)
    send(db, c, kind="booking_reminder", dedupe_key=f"reminder:{res.id}:{p['starts_at']}:{p.get('offset', '')}",
         text=f"Reminder: your table for {res.party_size} at {r.name} is booked for {when} (ref {res.ref}). "
              "Reply CANCEL if you can't make it.",
         template_params=[c.name or "there", r.name, when, str(res.party_size), res.ref], ref=("reservation", res.ref))


@handler("notify.payment_link")
def payment_link(db: Session, p: dict) -> None:
    pay = db.get(Payment, p["payment_id"])
    if not pay or pay.status != "created":
        return
    r = get_restaurant(db)
    if pay.order_id:
        o = db.get(Order, pay.order_id)
        if o.status != "awaiting_payment":
            return
        c = o.customer
        lines = [f"Your order {o.ref} at {r.name}:"] + [
            f"• {l['quantity']} x {l['name']}{' (' + l['detail'] + ')' if l['detail'] else ''} — {rupees(l['total'])}" for l in o.bill["lines"]]
        if o.discount_paise:
            lines.append(f"Discount ({o.bill['discount_name']}): -{rupees(o.discount_paise)}")
        lines += [f"{ch['name']}: {rupees(ch['amount'])}" for ch in o.bill["charges"]]
        lines += [f"GST: {rupees(o.tax_paise)}", f"Total: {rupees(o.total_paise)}"]
        what = "Pay" if pay.amount_paise == o.total_paise else f"Pay the advance of {rupees(pay.amount_paise)}"
        lines.append(f"{what} here: {pay.short_url}")
        lines.append("The restaurant confirms your order and preparation time once payment is verified.")
        ref = ("order", o.ref)
        params = [c.name or "there", r.name, rupees(pay.amount_paise), f"order {o.ref}", pay.short_url]
    else:
        res = db.get(Reservation, pay.reservation_id)
        if res.status != "held":
            return
        c = res.customer
        lines = [f"To confirm your table for {res.party_size} at {r.name} on {fmt_time(res.starts_at, db)}, "
                 f"please pay the deposit of {rupees(pay.amount_paise)} by {fmt_time(pay.expires_at, db)}:", pay.short_url,
                 "Your booking is confirmed only after the payment is verified."]
        ref = ("reservation", res.ref)
        params = [c.name or "there", r.name, rupees(pay.amount_paise), f"booking {res.ref}", pay.short_url]
    send(db, c, kind="payment_link", dedupe_key=f"paylink:{pay.id}", text="\n".join(lines), template_params=params, ref=ref)


@handler("notify.payment_received")
def payment_received(db: Session, p: dict) -> None:
    pay = db.get(Payment, p["payment_id"])
    if not pay or pay.status != "paid":
        return
    r = get_restaurant(db)
    if pay.order_id:
        o = db.get(Order, pay.order_id)
        if o.status in ("draft", "cancelled", "refunded"):
            return  # late payment: the refund message covers it
        send(db, o.customer, kind="order_update", dedupe_key=f"paid:{pay.id}",
             text=f"Payment of {rupees(pay.amount_paise)} received for order {o.ref}. ✅ The restaurant will confirm "
                  "your preparation time shortly.",
             template_params=[o.customer.name or "there", r.name, o.ref, "payment received"], ref=("order", o.ref))
    # Deposits: the booking confirmation (with QR) is sent by the confirmed-reservation notification.


@handler("notify.order")
def notify_order(db: Session, p: dict) -> None:
    o = db.get(Order, p["order_id"])
    event = p["event"]
    if not o or o.status != event:
        return
    r, c = get_restaurant(db), o.customer
    key = f"order:{o.id}:{event}"
    params = [c.name or "there", r.name, o.ref]
    if event == "accepted":
        token = qr.issue(db, order=o)
        ready = fmt_time(o.estimated_ready_at, db)
        paid = "Paid in full" if o.amount_paid_paise >= o.total_paise else (
            f"Paid {rupees(o.amount_paid_paise)}, balance {rupees(o.total_paise - o.amount_paid_paise)} at the counter"
            if o.amount_paid_paise else f"Pay {rupees(o.total_paise)} at the counter")
        lines = [f"{r.name} accepted your order {o.ref}! 👨‍🍳", *(f"• {l['quantity']} x {l['name']}" for l in o.bill["lines"]),
                 f"Payment: {paid}", f"Estimated ready: {ready}"]
        if r.pickup_instructions and o.order_type == "pickup":
            lines.append(r.pickup_instructions)
        lines += ["Show this QR code when you collect.", f"Can't open the image? {qr.url(token)}"]
        send(db, c, kind="order_update", dedupe_key=key, text="\n".join(lines), qr_png=qr.png(token),
             template_params=params + [f"accepted, ready around {ready}"], ref=("order", o.ref))
    elif event == "submitted":
        send(db, c, kind="order_update", dedupe_key=key,
             text=f"We've received your order {o.ref}. The restaurant will confirm it and the preparation time shortly.",
             template_params=params + ["received"], ref=("order", o.ref))
    elif event == "ready":
        send(db, c, kind="order_update", dedupe_key=key, text=f"Your order {o.ref} is ready! 🎉",
             template_params=params + ["ready"], ref=("order", o.ref))
    elif event == "cancelled":
        refund = " Any amount you paid will be refunded to your original payment method." if o.amount_paid_paise else ""
        send(db, c, kind="order_update", dedupe_key=key,
             text=f"Sorry, your order {o.ref} was cancelled ({o.cancel_reason or 'by the restaurant'}).{refund}",
             template_params=params + ["cancelled"], ref=("order", o.ref))


@handler("notify.refund")
def notify_refund(db: Session, p: dict) -> None:
    rf = db.get(Refund, p["refund_id"])
    if not rf or rf.status != "processed":
        return
    pay = db.get(Payment, rf.payment_id)
    owner = db.get(Order, pay.order_id) if pay.order_id else db.get(Reservation, pay.reservation_id)
    r = get_restaurant(db)
    send(db, owner.customer, kind="order_update", dedupe_key=f"refund:{rf.id}",
         text=f"Your refund of {rupees(rf.amount_paise)} ({owner.ref}) has been processed. It usually reaches your account in 5-7 working days.",
         template_params=[owner.customer.name or "there", r.name, owner.ref, f"refund of {rupees(rf.amount_paise)} processed"],
         ref=("payment", pay.ref))


@handler("notify.staff")
def notify_staff(db: Session, p: dict) -> None:
    send_staff(db, p["message"], f"staff:{p['alert_id']}")
