import json
from datetime import date, datetime, time, timedelta

import anthropic
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import config
from .db import now
from . import orders, waitlist
from .inbox import add_notice
from .models import Conversation, MenuItem, Order, Reservation
from .reservations import BookingError, available_times, book, find, reschedule, restaurant, set_status

MAX_ROUNDS = 6
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")


def _tool(name, description, params):
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": params, "required": list(params), "additionalProperties": False}}


DATE = {"type": "string", "description": "YYYY-MM-DD"}
TIME = {"type": "string", "description": "HH:MM, 24 hour"}
TOOLS = [
    _tool("check_availability", "Free booking times on a date for a number of guests.", {"date": DATE, "guests": {"type": "integer"}}),
    _tool("book_table", "Book a table. Only after the customer confirmed date, time, guests and name.",
          {"date": DATE, "time": TIME, "guests": {"type": "integer"}, "name": {"type": "string"}, "notes": {"type": ["string", "null"]}}),
    _tool("join_waitlist", "Put the customer on the waitlist when nothing is free at the time they want. If a table frees up they are booked automatically and get the QR on WhatsApp.",
          {"date": DATE, "time": TIME, "guests": {"type": "integer"}, "name": {"type": "string"}}),
    _tool("my_bookings", "Upcoming bookings for this customer's phone number.", {}),
    _tool("change_booking", "Move one of this customer's bookings.", {"ref": {"type": "string"}, "date": DATE, "time": TIME, "guests": {"type": "integer"}}),
    _tool("cancel_booking", "Cancel one of this customer's bookings after they confirm.", {"ref": {"type": "string"}}),
    _tool("get_menu", "The current menu with prices.", {}),
    _tool("order_food", "Set the dishes on this customer's food order, creating it if needed. Always send the full list, it replaces what was there. "
          "Use dish ids from get_menu. Link it to their booking when they have one.",
          {"booking_ref": {"type": ["string", "null"]},
           "items": {"type": "array", "items": {"type": "object", "properties": {"dish_id": {"type": "integer"}, "qty": {"type": "integer"},
                                                                                 "notes": {"type": ["string", "null"]}},
                                                "required": ["dish_id", "qty", "notes"], "additionalProperties": False}}}),
    _tool("my_order", "This customer's latest food order with the bill, payment status and payment link. Also use it when they say they have paid.", {}),
    _tool("confirm_order", "Confirm the current food order after the customer has seen the bill and agreed. The bill is sent automatically.", {}),
    _tool("cancel_order", "Cancel the current unpaid food order after the customer confirms.", {}),
    _tool("talk_to_staff", "Hand the chat to restaurant staff when the customer asks for a person, complains, or you can't help.",
          {"reason": {"type": "string"}}),
]


class Turn:
    def __init__(self, db: Session, convo, channel: str):
        self.db, self.convo, self.channel, self.booked_ids, self.order_ids = db, convo, channel, [], []

    def own(self, ref: str) -> Reservation:
        reservation = find(self.db, ref)
        if reservation.phone != self.convo.phone:
            raise BookingError("I can only find bookings made from this number")
        return reservation

    def notice(self, text: str) -> None:
        add_notice(self.db, f"{text} ({'call' if self.channel == 'phone' else 'WhatsApp'} {self.convo.phone})")

    def order(self) -> Order | None:
        return self.db.scalar(select(Order).where(Order.phone == self.convo.phone, Order.status.in_(orders.EDITABLE),
                                                  Order.payment_status == "unpaid").order_by(Order.id.desc()))

    def current_order(self) -> Order:
        order = self.order()
        if not order:
            raise BookingError("This customer has no open food order")
        return order

    def run(self, name: str, args: dict):
        start = lambda: datetime.combine(date.fromisoformat(args["date"]), time.fromisoformat(args["time"]))
        if name == "check_availability":
            times = available_times(self.db, args["guests"], date.fromisoformat(args["date"]))
            return {"free_times": [t.strftime("%H:%M") for t in times] or "nothing free that day"}
        if name == "book_table":
            reservation = book(self.db, name=args["name"], phone=self.convo.phone, guests=args["guests"], start=start(),
                               source=self.channel, notes=args.get("notes") or "")
            self.booked_ids.append(reservation.id)
            waitlist.mark_booked(self.db, self.convo.phone, reservation.starts_at.date())
            self.notice(f"{reservation.name} booked {reservation.starts_at:%a %d %b %I:%M %p} for {reservation.guests}, ref {reservation.ref}")
            return {"booked": True, "ref": reservation.ref, "table": reservation.table.name, "note": "A QR confirmation is sent automatically."}
        if name == "my_bookings":
            rows = self.db.scalars(select(Reservation).where(Reservation.phone == self.convo.phone, Reservation.status == "confirmed",
                                                             Reservation.starts_at > now()).order_by(Reservation.starts_at))
            return [{"ref": r.ref, "when": r.starts_at.strftime("%a %d %b %H:%M"), "guests": r.guests} for r in rows]
        if name == "change_booking":
            reservation = reschedule(self.db, self.own(args["ref"]), guests=args["guests"], start=start())
            self.booked_ids.append(reservation.id)
            self.notice(f"{reservation.name} moved booking {reservation.ref} to {reservation.starts_at:%a %d %b %I:%M %p}, {reservation.guests} guests")
            return {"changed": True, "ref": reservation.ref, "when": reservation.starts_at.strftime("%a %d %b %H:%M")}
        if name == "cancel_booking":
            reservation = set_status(self.db, self.own(args["ref"]), "cancelled")
            self.notice(f"{reservation.name} cancelled booking {reservation.ref} for {reservation.starts_at:%a %d %b %I:%M %p}")
            return {"cancelled": True}
        if name == "join_waitlist":
            entry = waitlist.join(self.db, name=args["name"], phone=self.convo.phone, guests=args["guests"], wanted_at=start())
            self.notice(f"{entry.name} joined the waitlist for {entry.wanted_at:%a %d %b %I:%M %p}, {entry.guests} guests")
            return {"on_waitlist": True}
        if name == "get_menu":
            items = self.db.scalars(select(MenuItem).where(MenuItem.available).order_by(MenuItem.category, MenuItem.name))
            return [{"dish_id": i.id, "dish": i.name, "also_called": i.other_names, "category": i.category, "price": f"Rs {i.price}", "veg": i.veg, "about": i.description} for i in items]
        if name == "order_food":
            order = self.order()
            reservation = self.own(args["booking_ref"]) if args.get("booking_ref") else None
            if not order:
                order = orders.create(self.db, name=self.convo.name or "Guest", phone=self.convo.phone,
                                      reservation=reservation, source=self.channel)
            elif reservation:
                order.reservation = reservation
            orders.set_items(self.db, order, [(i["dish_id"], i["qty"], i.get("notes") or "") for i in args["items"]])
            if order.status == "confirmed":
                self.order_ids.append(order.id)
            return {"bill": orders.bill_text(self.db, order), "status": order.status}
        if name == "my_order":
            order = self.db.scalar(select(Order).where(Order.phone == self.convo.phone, Order.status != "cancelled").order_by(Order.id.desc()))
            if not order:
                raise BookingError("This customer has no food order")
            if orders.refresh_payment(self.db, order):
                orders.notify_paid(self.db, order)
            return {"bill": orders.bill_text(self.db, order), "status": order.status, "payment": order.payment_status,
                    "pay_link": order.payment_link_url or None}
        if name == "confirm_order":
            order = orders.set_status(self.db, self.current_order(), "confirmed")
            self.order_ids.append(order.id)
            self.notice(f"{order.name} confirmed food order {order.ref}, Rs {order.total}")
            return {"confirmed": True, "note": "The bill is sent automatically."}
        if name == "cancel_order":
            order = orders.set_status(self.db, self.current_order(), "cancelled")
            self.notice(f"{order.name} cancelled food order {order.ref}")
            return {"cancelled": True}
        if name == "talk_to_staff":
            self.convo.needs_staff = True
            self.notice(f"{self.convo.name or self.convo.phone} needs staff: {args['reason']}")
            return {"handed_over": True}
        return {"error": "unknown tool"}

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        try:
            return json.dumps(self.run(name, args), default=str), False
        except BookingError as e:
            self.db.rollback()
            alternatives = f" Free nearby: {', '.join(t.strftime('%H:%M') for t in e.alternatives)}" if e.alternatives else ""
            return json.dumps({"error": e.message + alternatives}), True
        except HTTPException as e:
            self.db.rollback()
            return json.dumps({"error": e.detail}), True
        except (ValueError, KeyError) as e:
            self.db.rollback()
            return json.dumps({"error": f"bad input: {e}"}), True


CHANNEL_RULES = {
    "whatsapp": "You are chatting with customers on WhatsApp. Reply in the customer's language (English or Hindi). "
                "Keep replies short and friendly, plain text.",
    "phone": "You are answering a phone call and your words are read aloud. Use one to three short sentences, "
             "with no lists, symbols, emojis or links. If the caller speaks Hindi, reply in Hindi written in Devanagari, otherwise English. "
             "Say booking references letter by letter. Confirmations and bills are sent to the caller on WhatsApp. "
             "talk_to_staff transfers the call to a person.",
}


def system_prompt(db: Session, channel: str) -> str:
    r = restaurant(db)
    hours = "; ".join(f"{day}: {', '.join('-'.join(w) for w in windows) or 'closed'}" for day, windows in r.hours.items())
    return f"""You are the receptionist for {r.name}, a restaurant.
{CHANNEL_RULES[channel]}
Use the tools for availability, bookings and the menu. Never make up times, tables, prices or booking references.
Before booking, confirm date, time, number of guests and the customer's name.
Customers can pre-order food, with or without a booking. Match what they ask for to dishes from get_menu, and ask if unsure.
Show them the bill from order_food and only call confirm_order once they agree. They can change the order until it is paid.
If the customer asks for a person, complains, or you cannot help, use talk_to_staff.
Only talk about this restaurant.

Today is {now():%A %d %B %Y}, time {now():%H:%M}.
Opening hours: {hours}.
Address: {r.address or 'not given'}. Phone: {r.phone or 'not given'}.
About: {r.about or 'nothing more'}"""


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config().anthropic_api_key, timeout=30, max_retries=2)


def reply(db: Session, convo, text: str, channel: str = "whatsapp") -> tuple[str, Turn]:
    turn = Turn(db, convo, channel)
    history = list(convo.history) + [{"role": "user", "content": text}]
    model = config().anthropic_model
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if model in FALLBACK_MODELS else {}
    answer, system = "", system_prompt(db, channel)
    for _ in range(MAX_ROUNDS):
        db.commit()
        response = client().beta.messages.create(model=model, max_tokens=2000, system=system, tools=TOOLS,
                                                 messages=[{"role": m["role"], "content": m["content"]} for m in history], output_config={"effort": "low"}, **extra)
        history.append({"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in response.content]})
        answer = " ".join(b.text for b in response.content if b.type == "text").strip()
        calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            break
        results = []
        for c in calls:
            content, is_error = turn.call(c.name, dict(c.input))
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": content, "is_error": is_error})
        history.append({"role": "user", "content": results})
    if history[-1]["role"] == "user":
        history.append({"role": "assistant", "content": [{"type": "text", "text": answer or "Sorry, could you say that again?"}]})
    convo.history = history
    if convo.needs_staff and not answer and channel == "whatsapp":
        answer = "I have passed your message to our staff. Someone will reply here soon."
    return answer or "Sorry, could you say that again?", turn
