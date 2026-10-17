import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from . import razorpay, whatsapp
from .auth import current_user
from .db import Session as DbSession
from .db import get_db, now
from .models import MenuItem, Order, OrderItem, Reservation
from .reservations import REF_CHARS, BookingError, find, normalize_phone, restaurant

router = APIRouter(prefix="/api/orders")
NEXT_STATUS = {"open": {"confirmed", "cancelled"}, "confirmed": {"preparing", "cancelled"}, "preparing": {"ready"}, "ready": {"served"}}
EDITABLE = {"open", "confirmed"}
ACTIVE = ("open", "confirmed", "preparing", "ready")
MAX_QTY = 20


def new_ref(db: Session) -> str:
    while True:
        ref = "".join(secrets.choice(REF_CHARS) for _ in range(6))
        if not db.scalar(select(Order.id).where(Order.ref == ref)):
            return ref


def create(db: Session, *, name: str, phone: str, reservation: Reservation | None = None, source: str = "dashboard") -> Order:
    order = Order(ref=new_ref(db), name=name, phone=phone, reservation=reservation, source=source, status="open", payment_status="unpaid")
    db.add(order)
    return order


def refresh_payment(db: Session, order: Order) -> bool:
    if order.payment_status == "paid" or not order.payment_link_id:
        return False
    link_id, expected = order.payment_link_id, order.total * 100
    db.commit()
    link = razorpay.fetch_link(link_id)
    if link.get("status") != "paid" or link.get("amount_paid") != expected:
        return False
    payment_id = next((p["payment_id"] for p in reversed(link.get("payments") or []) if p.get("payment_id")), "")
    changed = db.execute(update(Order).where(Order.id == order.id, Order.payment_status == "unpaid", Order.payment_link_id == link_id)
                         .values(payment_status="paid", payment_id=payment_id, paid_at=now())).rowcount
    db.commit()
    db.refresh(order)
    return changed == 1


def release_link(db: Session, order: Order) -> None:
    if not order.payment_link_id or order.payment_status == "paid":
        return
    link_id = order.payment_link_id
    db.commit()
    try:
        razorpay.cancel_link(link_id)
    except razorpay.RazorpayError:
        if refresh_payment(db, order):
            notify_paid(db, order)
            raise BookingError("This order has just been paid online")
        if razorpay.fetch_link(link_id).get("status") not in ("cancelled", "expired"):
            raise BookingError("Could not cancel the old payment link, please try again")
    order.payment_link_id = order.payment_link_url = ""
    db.commit()


def payment_link(db: Session, order: Order) -> str:
    if not order.payment_link_url:
        place = restaurant(db).name
        details = dict(amount=order.total, reference=f"{order.ref}-{secrets.token_hex(3)}", description=f"Order {order.ref} at {place}",
                       name=order.name, phone=order.phone)
        db.commit()
        link = razorpay.create_link(**details)
        order.payment_link_id, order.payment_link_url = link["id"], link["short_url"]
        db.commit()
    return order.payment_link_url


def set_items(db: Session, order: Order, items: list[tuple[int, int, str]]) -> Order:
    if order.payment_status == "paid" or order.status not in EDITABLE:
        raise BookingError("This order can't be changed any more")
    release_link(db, order)
    lines = []
    for menu_item_id, qty, notes in items:
        dish = db.get(MenuItem, menu_item_id)
        if not dish:
            raise BookingError(f"Dish {menu_item_id} is not on the menu")
        if not dish.available:
            raise BookingError(f"{dish.name} is out of stock today")
        if not 1 <= qty <= MAX_QTY:
            raise BookingError(f"Quantity for {dish.name} must be between 1 and {MAX_QTY}")
        lines.append(OrderItem(menu_item=dish, name=dish.name, price=dish.price, qty=qty, notes=(notes or "")[:200]))
    order.items = lines
    order.total = sum(line.price * line.qty for line in lines)
    db.commit()
    return order


def set_status(db: Session, order: Order, status: str) -> Order:
    if status not in NEXT_STATUS.get(order.status, set()):
        raise BookingError(f"A {order.status} order can't be marked {status}")
    if status == "confirmed" and not order.items:
        raise BookingError("Add at least one dish before confirming")
    if status == "cancelled":
        release_link(db, order)
        if order.payment_status == "paid":
            raise BookingError("This order is already paid. Refund it in Razorpay first.")
    order.status = status
    db.commit()
    return order


def ready_note(db: Session, order: Order) -> str:
    slowest = max((line.menu_item.prep_minutes if line.menu_item else 0 for line in order.items), default=0)
    target = restaurant(db).prep_target_minutes
    if order.reservation:
        head_start = max(0, int((order.reservation.starts_at - now()).total_seconds() // 60))
        if slowest <= head_start + target:
            return f"Your food will be served within {target} minutes of your arrival."
        return f"Your food will take about {slowest - head_start} minutes after you arrive."
    if slowest <= target:
        return f"Your food will be ready in {target} minutes."
    return f"Your food will be ready in about {slowest} minutes."


def start_by(order: Order) -> datetime | None:
    if not order.reservation or not order.items:
        return None
    slowest = max(line.menu_item.prep_minutes if line.menu_item else 0 for line in order.items)
    return order.reservation.starts_at - timedelta(minutes=slowest)


def bill_text(db: Session, order: Order) -> str:
    lines = [f"Order {order.ref} at {restaurant(db).name}"]
    if order.reservation:
        lines.append(f"For booking {order.reservation.ref}, {order.reservation.starts_at:%a %d %b %I:%M %p}")
    lines.append("")
    for line in order.items:
        note = f" ({line.notes})" if line.notes else ""
        lines.append(f"{line.qty} x {line.name}{note}: Rs {line.price * line.qty}")
    lines += ["", f"Total: Rs {order.total}", ready_note(db, order)]
    return "\n".join(lines)


def send_order_confirmation(order_id: int) -> None:
    with DbSession() as db:
        order = db.get(Order, order_id)
        if not order or not order.phone or order.status != "confirmed":
            return
        message = "Your order is confirmed.\n\n" + bill_text(db, order)
        if order.payment_status == "unpaid" and razorpay.enabled():
            try:
                message += "\n\nPay online: " + payment_link(db, order)
            except Exception as e:
                whatsapp.log_failure(db, "razorpay", f"Payment link for order {order.ref}: {e}")
                message += "\n\nYou can pay at the restaurant."
        send(db, order, message, "whatsapp_order")


def send(db: Session, order: Order, message: str, kind: str) -> None:
    can_send = whatsapp.can_message_freely(db, order.phone)
    db.commit()
    try:
        if not can_send:
            raise whatsapp.WhatsAppError("customer has not messaged in 24 hours")
        whatsapp.send_text(order.phone, message)
    except Exception as e:
        whatsapp.log_failure(db, kind, f"Order {order.ref} for {order.phone}: {e}")


def notify_paid(db: Session, order: Order) -> None:
    if order.phone:
        send(db, order, f"Payment of Rs {order.total} received for order {order.ref}. Thank you!", "whatsapp_payment")


def check_payment(order_id: int) -> None:
    with DbSession() as db:
        order = db.get(Order, order_id)
        try:
            if order and refresh_payment(db, order):
                notify_paid(db, order)
        except Exception as e:
            whatsapp.log_failure(db, "razorpay", f"Checking payment for order {order.ref}: {e}")


def check_pending_payments() -> None:
    with DbSession() as db:
        ids = db.scalars(select(Order.id).where(Order.payment_link_id != "", Order.payment_status == "unpaid", Order.status != "cancelled",
                                                Order.created_at > now() - timedelta(days=2))).all()
        db.commit()
    for order_id in ids:
        check_payment(order_id)


def find_order(db: Session, ref: str) -> Order:
    order = db.scalar(select(Order).where(Order.ref == ref.strip().upper()))
    if not order:
        raise HTTPException(404, "Order not found")
    return order


def order_out(db: Session, o: Order) -> dict:
    return {"id": o.id, "ref": o.ref, "name": o.name, "phone": o.phone, "status": o.status, "payment_status": o.payment_status,
            "total": o.total, "source": o.source, "created_at": o.created_at, "booking": o.reservation.ref if o.reservation else None,
            "booking_at": o.reservation.starts_at if o.reservation else None,
            "table": o.reservation.table.name if o.reservation and o.reservation.table else None,
            "start_by": start_by(o), "payment_link": o.payment_link_url, "payment_id": o.payment_id, "paid_at": o.paid_at, "ready_note": ready_note(db, o) if o.items else "",
            "items": [{"menu_item_id": i.menu_item_id, "name": i.name, "price": i.price, "qty": i.qty, "notes": i.notes} for i in o.items]}


class LineIn(BaseModel):
    menu_item_id: int
    qty: int = Field(ge=1, le=MAX_QTY)
    notes: str = Field("", max_length=200)


class OrderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field("", max_length=20)
    booking: str = ""
    items: list[LineIn] = Field(min_length=1)


def bad(e: BookingError) -> HTTPException:
    return HTTPException(409, e.message)


def send_later(background: BackgroundTasks, db: Session, order: Order) -> dict:
    out = order_out(db, order)
    if order.status == "confirmed":
        db.close()
        background.add_task(send_order_confirmation, order.id)
    return out


@router.get("")
def list_orders(day: date | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    query = select(Order).outerjoin(Reservation).order_by(func.coalesce(Reservation.starts_at, Order.created_at))
    if day:
        start = datetime.combine(day, datetime.min.time())
        when = func.coalesce(Reservation.starts_at, Order.created_at)
        query = query.where(when >= start, when < start + timedelta(days=1))
    else:
        query = query.where(or_(Order.status.in_(ACTIVE), Order.payment_status == "unpaid"), Order.status != "cancelled")
    return [order_out(db, o) for o in db.scalars(query)]


@router.post("")
def add_order(body: OrderIn, background: BackgroundTasks, db: Session = Depends(get_db), _=Depends(current_user)):
    try:
        phone = normalize_phone(body.phone) if body.phone.strip() else ""
        reservation = find(db, body.booking) if body.booking.strip() else None
        order = create(db, name=body.name, phone=phone, reservation=reservation)
        set_items(db, order, [(i.menu_item_id, i.qty, i.notes) for i in body.items])
        set_status(db, order, "confirmed")
    except BookingError as e:
        db.rollback()
        raise bad(e)
    return send_later(background, db, order)


@router.put("/{ref}/items")
def change_items(ref: str, items: list[LineIn], db: Session = Depends(get_db), _=Depends(current_user)):
    if not items:
        raise HTTPException(422, "An order needs at least one dish. Cancel it instead.")
    try:
        return order_out(db, set_items(db, find_order(db, ref), [(i.menu_item_id, i.qty, i.notes) for i in items]))
    except BookingError as e:
        raise bad(e)


@router.post("/{ref}/status")
def change_status(ref: str, status: str, background: BackgroundTasks, db: Session = Depends(get_db), _=Depends(current_user)):
    try:
        return send_later(background, db, set_status(db, find_order(db, ref), status))
    except BookingError as e:
        raise bad(e)


@router.post("/{ref}/paid")
def mark_paid(ref: str, db: Session = Depends(get_db), _=Depends(current_user)):
    order = find_order(db, ref)
    if order.status == "cancelled":
        raise HTTPException(409, "This order is cancelled")
    try:
        release_link(db, order)
    except BookingError as e:
        raise bad(e)
    if order.payment_status != "paid":
        order.payment_status, order.payment_id, order.paid_at = "paid", "cash", now()
        db.commit()
    return order_out(db, order)


@router.post("/{ref}/check-payment")
def check_payment_now(ref: str, db: Session = Depends(get_db), _=Depends(current_user)):
    order = find_order(db, ref)
    order_id = order.id
    db.close()
    check_payment(order_id)
    with DbSession() as fresh:
        return order_out(fresh, fresh.get(Order, order_id))
