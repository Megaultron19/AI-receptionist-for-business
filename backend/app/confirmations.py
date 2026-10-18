import hashlib
import io
import secrets

import segno
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import whatsapp
from .db import Session as DbSession
from .db import now
from .models import Reservation
from .reservations import restaurant

QR_PREFIX = "RR:"


def qr_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_qr(db: Session, reservation: Reservation) -> bytes:
    token = secrets.token_urlsafe(24)
    reservation.qr_hash = qr_hash(token)
    db.commit()
    buffer = io.BytesIO()
    segno.make(QR_PREFIX + token, error="m").save(buffer, kind="png", scale=8, border=3)
    return buffer.getvalue()


def details(db: Session, reservation: Reservation) -> list[str]:
    r = restaurant(db)
    return [reservation.name, r.name, reservation.ref, reservation.starts_at.strftime("%a %d %b, %I:%M %p"),
            str(reservation.guests), reservation.table.name if reservation.table else "Assigned on arrival"]


def send_confirmation(reservation_id: int) -> None:
    with DbSession() as db:
        reservation = db.get(Reservation, reservation_id)
        if not reservation or reservation.status != "confirmed":
            return
        png = new_qr(db, reservation)
        name, place, ref, when, guests, table = details(db, reservation)
        caption = (f"Your table at {place} is booked.\nBooking: {ref}\nWhen: {when}\nGuests: {guests}\nTable: {table}\n"
                   "Show this QR code at the door.")
        free_window = whatsapp.can_message_freely(db, reservation.phone)
        db.commit()
        try:
            media_id = whatsapp.upload_image(png)
            if free_window:
                whatsapp.send_image(reservation.phone, media_id, caption)
            elif whatsapp.config().whatsapp_confirmation_template:
                whatsapp.send_template(reservation.phone, media_id, [name, place, ref, when, guests, table])
            else:
                raise whatsapp.WhatsAppError("customer has not messaged in 24 hours and no confirmation template is set")
        except Exception as e:
            whatsapp.log_failure(db, "whatsapp_confirmation", f"Booking {ref} for {reservation.phone}: {e}")


def check_in(db: Session, code: str) -> dict:
    token = code.strip().removeprefix(QR_PREFIX)
    reservation = db.scalar(select(Reservation).where(Reservation.qr_hash == qr_hash(token))) if token else None
    if not reservation:
        return {"ok": False, "message": "This QR code is not valid"}
    info = {"ref": reservation.ref, "name": reservation.name, "guests": reservation.guests,
            "time": reservation.starts_at.strftime("%I:%M %p"), "table": reservation.table.name if reservation.table else None}
    if reservation.checked_in_at:
        return {"ok": False, "message": f"Already checked in at {reservation.checked_in_at:%I:%M %p}", **info}
    if reservation.status != "confirmed":
        return {"ok": False, "message": f"This booking is {reservation.status.replace('_', ' ')}", **info}
    if reservation.starts_at.date() != now().date():
        return {"ok": False, "message": f"This booking is for {reservation.starts_at:%d %b}", **info}
    reservation.status, reservation.checked_in_at = "arrived", now()
    db.commit()
    return {"ok": True, "message": "Checked in", **info}
