"""Tools the AI receptionist can call. Each one goes through the same validated domain services as the
dashboard, so the model can never invent a table, a price, a booking or a payment: it only reports what
these functions return. Errors come back as plain messages for the model to relay."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..conversations import service as convo_service
from ..conversations.models import Conversation
from ..core.errors import Conflict, DomainError
from ..customers.models import Customer
from ..customers.service import record_opt_in
from ..menu.matching import match_item, match_option
from ..menu.models import MenuCategory, MenuItem
from ..orders import service as orders
from ..notifications.service import can_whatsapp
from ..orders.billing import rupees
from ..orders.models import Order
from ..reservations import engine
from ..reservations.models import Reservation
from ..restaurant.service import get_restaurant, tz
from .llm import ToolSpec


@dataclass
class ToolContext:
    db: Session
    customer: Customer
    convo: Conversation
    channel: str
    flags: dict[str, Any] = field(default_factory=dict)

    @property
    def actor(self):
        return ("ai", self.convo.id)


S = {"type": "string"}
NS = {"type": ["string", "null"]}
I = {"type": "integer"}
NI = {"type": ["integer", "null"]}
DATE = {"type": "string", "description": "YYYY-MM-DD (restaurant's local date)"}
TIME = {"type": "string", "description": "HH:MM 24-hour local time"}

TOOLS: dict[str, tuple[ToolSpec, Callable[[ToolContext, dict], Any]]] = {}


def tool(name: str, description: str, params: dict[str, Any] | None = None, channels: tuple[str, ...] = ("voice", "whatsapp")):
    def register(fn):
        TOOLS[name] = (ToolSpec(name, description, params or {}), fn, channels)
        return fn
    return register


def specs(channel: str) -> list[ToolSpec]:
    return [spec for spec, _, chans in TOOLS.values() if channel in chans]


def run(ctx: ToolContext, name: str, args: dict) -> tuple[str, bool]:
    """Execute a tool inside a savepoint. Returns (json result, is_error)."""
    entry = TOOLS.get(name)
    if not entry or ctx.channel not in entry[2]:
        return json.dumps({"error": f"unknown tool {name}"}), True
    try:
        with ctx.db.begin_nested():
            result = entry[1](ctx, args)
        return json.dumps(result, default=str, ensure_ascii=False), False
    except (DomainError, ValueError, KeyError) as e:
        msg = e.message if isinstance(e, DomainError) else f"invalid input: {e}"
        return json.dumps({"error": msg}, ensure_ascii=False), True



def _local(ctx: ToolContext, d: str, t: str) -> datetime:
    return datetime.combine(date.fromisoformat(d), time.fromisoformat(t), tz(get_restaurant(ctx.db)))


def _fmt(ctx: ToolContext, dt: datetime) -> str:
    return dt.astimezone(tz(get_restaurant(ctx.db))).strftime("%a %d %b %Y, %H:%M")


def _res_out(ctx: ToolContext, res: Reservation) -> dict:
    return {"ref": res.ref, "status": res.status, "when": _fmt(ctx, res.starts_at), "party_size": res.party_size,
            "deposit_due": rupees(res.deposit_paise) if res.status == "held" and res.hold_reason == "deposit" else None,
            "hold_expires": _fmt(ctx, res.hold_expires_at) if res.status == "held" and res.hold_expires_at else None}


def _own_reservation(ctx: ToolContext, ref: str) -> Reservation:
    res = engine.get_by_ref(ctx.db, ref, for_update=True)
    if res.customer_id != ctx.customer.id:
        raise DomainError("I can only find bookings made with this phone number.")
    return res


def _current_order(ctx: ToolContext, *, required: bool = True) -> Order | None:
    ref = ctx.convo.state.get("order_ref")
    o = orders.get_order(ctx.db, ref, for_update=True) if ref else None
    if o and o.customer_id != ctx.customer.id:
        o = None
    if required and not o:
        raise DomainError("There is no order in progress. Start one first.")
    return o


def _order_out(ctx: ToolContext, o: Order) -> dict:
    b = o.bill
    out = {
        "ref": o.ref, "status": o.status, "order_type": o.order_type,
        "lines": [{"line_id": l.id, "dish": l.item_name, "option": l.variant_name or None,
                   "addons": [a["name"] for a in l.addons], "quantity": l.quantity, "instructions": l.instructions or None,
                   "line_total": rupees(l.unit_price_paise * l.quantity)} for l in o.items],
        "subtotal": rupees(o.subtotal_paise),
        "discount": f"{b.get('discount_name')}: -{rupees(o.discount_paise)}" if o.discount_paise else None,
        "charges": [f"{c['name']}: {rupees(c['amount'])}" for c in b.get("charges", [])],
        "gst": rupees(o.tax_paise), "total": rupees(o.total_paise),
        "pay_now": rupees(o.amount_due_paise) if o.amount_due_paise else "nothing (pay at the restaurant)",
    }
    if o.items:
        q = orders.kitchen_quote(ctx.db, o)
        out["preparation_estimate"] = {
            "minutes": q["estimate_minutes"], "target_minutes": q["target_minutes"], "meets_target": q["meets_target"],
            "reasons": q["reasons"], "note": "An estimate only; the restaurant confirms the time when it accepts the order."}
    return out


def _set_outcome(ctx: ToolContext, outcome: str) -> None:
    order = {"info": 0, "callback": 1, "transferred": 1, "reservation": 2, "order": 2}
    if order.get(outcome, 0) >= order.get(ctx.flags.get("outcome", "info"), 0):
        ctx.flags["outcome"] = outcome



@tool("check_availability", "Check real table availability. Give `time` to check one time (returns alternatives if it's "
      "taken) or null to list all free times that day.", {"date": DATE, "time": {**NS, "description": "HH:MM or null"}, "party_size": I})
def check_availability(ctx: ToolContext, a: dict) -> dict:
    day = date.fromisoformat(a["date"])
    times = engine.available_times(ctx.db, a["party_size"], day)
    zone = tz(get_restaurant(ctx.db))
    fmt = [t.astimezone(zone).strftime("%H:%M") for t in times]
    if a.get("time"):
        wanted = _local(ctx, a["date"], a["time"])
        if wanted in times:
            return {"available": True, "date": a["date"], "time": a["time"], "party_size": a["party_size"]}
        alts = engine.suggest_alternatives(ctx.db, a["party_size"], wanted)
        return {"available": False, "alternatives": [_fmt(ctx, t) for t in alts] or "no free tables in the next few days"}
    return {"date": a["date"], "party_size": a["party_size"], "free_times": fmt or "fully booked or closed that day"}


@tool("create_reservation", "Book a table. Only after the customer has confirmed date, time, party size and name.",
      {"date": DATE, "time": TIME, "party_size": I, "name": S, "special_requests": NS})
def create_reservation(ctx: ToolContext, a: dict) -> dict:
    if a["name"].strip() and not ctx.customer.name:
        ctx.customer.name = a["name"].strip()[:120]
    start = _local(ctx, a["date"], a["time"])
    try:
        res = engine.create_reservation(ctx.db, customer=ctx.customer, party=a["party_size"], start=start, source=ctx.channel,
                                        actor=ctx.actor, notes=a.get("special_requests") or "")
    except Conflict:
        alts = engine.suggest_alternatives(ctx.db, a["party_size"], start)
        raise DomainError("That time was just taken. Free times: " + (", ".join(_fmt(ctx, t) for t in alts) or "none soon"))
    _set_outcome(ctx, "reservation")
    out = _res_out(ctx, res)
    out["next_step"] = ("Deposit required: a payment link is being sent; the booking is confirmed only after payment."
                        if res.status == "held" else "Confirmed. A confirmation with QR code is sent on WhatsApp if permitted.")
    return out


@tool("find_my_reservations", "List this customer's upcoming bookings (matched by their phone number).")
def find_my_reservations(ctx: ToolContext, a: dict) -> dict:
    rows = ctx.db.scalars(select(Reservation).where(Reservation.customer_id == ctx.customer.id,
                                                    Reservation.status.in_(("held", "confirmed")),
                                                    Reservation.starts_at > datetime.now(tz(get_restaurant(ctx.db))))
                          .order_by(Reservation.starts_at)).all()
    return {"reservations": [_res_out(ctx, r) for r in rows]}


@tool("cancel_reservation", "Cancel one of this customer's bookings after they confirm.", {"ref": S})
def cancel_reservation(ctx: ToolContext, a: dict) -> dict:
    res = _own_reservation(ctx, a["ref"])
    engine.customer_cancel(ctx.db, res, actor=ctx.actor)
    return {"cancelled": True, "ref": res.ref}


@tool("reschedule_reservation", "Move one of this customer's bookings to a new date/time and/or party size.",
      {"ref": S, "date": DATE, "time": TIME, "party_size": I})
def reschedule_reservation(ctx: ToolContext, a: dict) -> dict:
    res = _own_reservation(ctx, a["ref"])
    start = _local(ctx, a["date"], a["time"])
    try:
        engine.reschedule(ctx.db, res, start=start, party=a["party_size"], actor=ctx.actor)
    except Conflict:
        alts = engine.suggest_alternatives(ctx.db, a["party_size"], start)
        raise DomainError("No table at that time. Free times: " + (", ".join(_fmt(ctx, t) for t in alts) or "none soon"))
    _set_outcome(ctx, "reservation")
    return _res_out(ctx, res)


@tool("respond_to_waitlist_offer", "Accept or decline a table we offered from the waitlist.", {"ref": S, "accept": {"type": "boolean"}})
def respond_to_offer(ctx: ToolContext, a: dict) -> dict:
    res = _own_reservation(ctx, a["ref"])
    if res.status != "held" or res.hold_reason != "waitlist":
        raise DomainError("There is no open table offer with that reference.")
    if a["accept"]:
        engine.confirm_hold(ctx.db, res, actor=ctx.actor)
        _set_outcome(ctx, "reservation")
    else:
        engine.transition(ctx.db, res, "cancelled", actor=ctx.actor, reason="waitlist offer declined")
    return _res_out(ctx, res)


@tool("join_waitlist", "Add the customer to the waitlist when nothing is free; we message them if a table opens.",
      {"date": DATE, "earliest_time": TIME, "latest_time": TIME, "party_size": I})
def join_waitlist(ctx: ToolContext, a: dict) -> dict:
    e = engine.add_to_waitlist(ctx.db, customer=ctx.customer, party=a["party_size"], earliest=_local(ctx, a["date"], a["earliest_time"]),
                               latest=_local(ctx, a["date"], a["latest_time"]), source=ctx.channel, actor=ctx.actor)
    return {"waitlisted": True, "id": e.id, "note": "We'll message on WhatsApp if a table frees up; they must confirm quickly."}



@tool("get_menu", "Current menu with prices and availability. Use `category` to narrow, or null for everything.",
      {"category": NS})
def get_menu(ctx: ToolContext, a: dict) -> dict:
    stmt = select(MenuItem).join(MenuCategory).where(MenuItem.active, MenuCategory.active).order_by(MenuCategory.sort, MenuItem.sort)
    items = ctx.db.scalars(stmt).all()
    if a.get("category"):
        items = [i for i in items if a["category"].lower() in i.category.name.lower()] or items
    out: dict[str, list] = {}
    for i in items:
        entry = {"dish": i.name, "available": i.available}
        if i.name_hi:
            entry["hindi"] = i.name_hi
        entry["price"] = ", ".join(f"{v.name} {rupees(v.price_paise)}" for v in i.variants if v.available) if i.variants else rupees(i.price_paise)
        if i.dietary:
            entry["dietary"] = i.dietary
        if i.allergens:
            entry["allergens"] = i.allergens
        if i.description:
            entry["description"] = i.description[:160]
        if i.addon_groups:
            entry["options"] = {g.name: [f"{x.name}" + (f" +{rupees(x.price_paise)}" if x.price_paise else "") for x in g.addons if x.available]
                                for g in i.addon_groups}
        out.setdefault(i.category.name, []).append(entry)
    return {"menu": out, "note": "Dietary and allergen details are as supplied by the restaurant."}


@tool("start_order", "Start a food pre-order (pickup, or dine-in for a booking). Reuses the open draft if there is one.",
      {"order_type": {"type": "string", "enum": ["pickup", "dine_in"]}, "reservation_ref": NS})
def start_order(ctx: ToolContext, a: dict) -> dict:
    o = _current_order(ctx, required=False)
    if o and o.status == "draft":
        return _order_out(ctx, o)
    res_id = None
    if a.get("reservation_ref"):
        res_id = _own_reservation(ctx, a["reservation_ref"]).id
    o = orders.create_draft(ctx.db, customer=ctx.customer, channel=ctx.channel, actor=ctx.actor, order_type=a["order_type"],
                            reservation_id=res_id)
    ctx.convo.state = {**ctx.convo.state, "order_ref": o.ref}
    return _order_out(ctx, o)


def _pick_item(ctx: ToolContext, dish: str) -> MenuItem:
    items = ctx.db.scalars(select(MenuItem).where(MenuItem.active)).all()
    m = match_item(dish, items)
    if m.status == "matched":
        return m.item
    if m.status == "ambiguous":
        raise DomainError(f"'{dish}' could be: {', '.join(c.name for c in m.candidates)}. Ask the customer which one.")
    hint = f" Similar: {', '.join(c.name for c in m.candidates)}." if m.candidates else ""
    raise DomainError(f"'{dish}' is not on our menu.{hint}")


def _pick_options(item: MenuItem, variant: str | None, addons: list[str]) -> tuple[int | None, list[int]]:
    variant_id = None
    if item.variants:
        if not variant:
            raise DomainError(f"{item.name} comes in {', '.join(v.name for v in item.variants if v.available)}. Ask which one.")
        v, cands = match_option(variant, item.variants)
        if not v:
            raise DomainError(f"{item.name} options are {', '.join(c.name for c in cands)}. Ask which one.")
        variant_id = v.id
    all_addons = [x for g in item.addon_groups for x in g.addons]
    ids = []
    for name in addons:
        x, cands = match_option(name, all_addons)
        if not x:
            raise DomainError(f"'{name}' isn't an option for {item.name}. Options: {', '.join(c.name for c in all_addons)}.")
        ids.append(x.id)
    return variant_id, ids


@tool("add_to_order", "Add a dish to the current order. Use the customer's words for dish/option/add-ons; the menu is matched "
      "on the server and ambiguity comes back as an error to clarify.",
      {"dish": S, "quantity": I, "option": {**NS, "description": "size/variant such as Half or Full, or null"},
       "addons": {"type": "array", "items": S}, "instructions": NS})
def add_to_order(ctx: ToolContext, a: dict) -> dict:
    o = _current_order(ctx)
    item = _pick_item(ctx, a["dish"])
    variant_id, addon_ids = _pick_options(item, a.get("option"), a.get("addons") or [])
    orders.add_item(ctx.db, o, item_id=item.id, quantity=a["quantity"], variant_id=variant_id, addon_ids=addon_ids,
                    instructions=a.get("instructions") or "", actor=ctx.actor)
    return _order_out(ctx, o)


@tool("change_order_line", "Change quantity (0 removes), option, add-ons or instructions of a line in the current order.",
      {"line_id": I, "quantity": NI, "option": NS, "addons": {"type": ["array", "null"], "items": S}, "instructions": NS})
def change_order_line(ctx: ToolContext, a: dict) -> dict:
    o = _current_order(ctx)
    line = next((l for l in o.items if l.id == a["line_id"]), None)
    if not line:
        raise DomainError("No such line in the order.")
    variant_id = addon_ids = None
    if a.get("option") is not None or a.get("addons") is not None:
        item = ctx.db.get(MenuItem, line.menu_item_id)
        variant_id, addon_ids = _pick_options(item, a.get("option") or line.variant_name or None,
                                              a["addons"] if a.get("addons") is not None else [x["name"] for x in line.addons])
    orders.update_item(ctx.db, o, line.id, actor=ctx.actor, quantity=a.get("quantity"), variant_id=variant_id,
                       addon_ids=addon_ids, instructions=a.get("instructions"))
    return _order_out(ctx, o)


@tool("view_order", "Current order summary with server-calculated bill and preparation estimate.")
def view_order(ctx: ToolContext, a: dict) -> dict:
    return _order_out(ctx, _current_order(ctx))


@tool("edit_confirmed_order", "Reopen an order that is waiting for payment so the customer can change it (old payment link is cancelled).")
def edit_confirmed_order(ctx: ToolContext, a: dict) -> dict:
    o = _current_order(ctx)
    orders.reopen_for_edit(ctx.db, o, actor=ctx.actor)
    return _order_out(ctx, o)


@tool("confirm_order", "Confirm the current order after reading the full summary and total to the customer and getting a yes. "
      "`pickup_time` HH:MM today or null for as soon as possible.", {"pickup_time": NS, "customer_gstin": NS})
def confirm_order(ctx: ToolContext, a: dict) -> dict:
    o = _current_order(ctx)
    when = None
    if a.get("pickup_time"):
        when = _local(ctx, datetime.now(tz(get_restaurant(ctx.db))).date().isoformat(), a["pickup_time"])
    orders.confirm(ctx.db, o, actor=ctx.actor, scheduled_for=when, gstin=a.get("customer_gstin") or "")
    _set_outcome(ctx, "order")
    out = _order_out(ctx, o)
    if o.status == "awaiting_payment":
        via = "WhatsApp" if can_whatsapp(ctx.db, ctx.customer, "payment_link") else "SMS from Razorpay"
        out["next_step"] = (f"A secure Razorpay payment link for {rupees(o.amount_due_paise)} is being sent by {via}. "
                            "The order goes to the kitchen only after the payment is verified, and the restaurant then "
                            "confirms the preparation time.")
    else:
        out["next_step"] = "Sent to the restaurant. They confirm the preparation time when they accept it."
    return out


@tool("cancel_order", "Cancel the current order if it hasn't been accepted by the restaurant yet.")
def cancel_order(ctx: ToolContext, a: dict) -> dict:
    o = _current_order(ctx)
    if o.status not in ("draft", "awaiting_payment", "payment_pending", "submitted"):
        raise DomainError("The restaurant has already started on this order; please speak to the staff.")
    orders.transition(ctx.db, o, "cancelled", actor=ctx.actor, reason="cancelled by customer")
    return {"cancelled": True, "ref": o.ref, "refund": "Any payment will be refunded automatically." if o.amount_paid_paise else None}


@tool("get_order_status", "Status of an order by reference (or the current one if ref is null).", {"ref": NS})
def get_order_status(ctx: ToolContext, a: dict) -> dict:
    o = orders.get_order(ctx.db, a["ref"]) if a.get("ref") else _current_order(ctx)
    if o.customer_id != ctx.customer.id:
        raise DomainError("I can only look up orders placed from this phone number.")
    out = {"ref": o.ref, "status": o.status, "paid": rupees(o.amount_paid_paise), "total": rupees(o.total_paise)}
    if o.estimated_ready_at:
        out["estimated_ready"] = _fmt(ctx, o.estimated_ready_at)
    return out



@tool("record_whatsapp_consent", "Record whether the customer agreed to receive booking/order messages (confirmations, "
      "reminders, payment links) on WhatsApp at this number.", {"agreed": {"type": "boolean"}})
def record_consent(ctx: ToolContext, a: dict) -> dict:
    if a["agreed"]:
        record_opt_in(ctx.customer, f"{ctx.channel}_verbal" if ctx.channel == "voice" else "whatsapp_chat")
    else:
        ctx.customer.whatsapp_opt_in = False
    return {"whatsapp_opt_in": ctx.customer.whatsapp_opt_in}


@tool("transfer_to_staff", "Hand the conversation to restaurant staff: customer asks for a person, has a complaint, or you "
      "can't complete their request.", {"reason": S})
def transfer_to_staff(ctx: ToolContext, a: dict) -> dict:
    r = get_restaurant(ctx.db)
    if ctx.channel == "voice" and r.transfer_number:
        ctx.flags["transfer"] = a["reason"]
        _set_outcome(ctx, "transferred")
        return {"transferring": True, "say": "Tell the caller you are connecting them now."}
    convo_service.handoff(ctx.db, ctx.convo, a["reason"])
    if ctx.channel == "voice":
        convo_service.request_callback(ctx.db, ctx.customer, a["reason"], source="voice")
        _set_outcome(ctx, "callback")
        return {"transferring": False, "callback_requested": True, "say": "Staff will call back soon."}
    return {"handed_off": True, "say": "A member of staff will reply here shortly."}


@tool("request_callback", "Ask staff to call the customer back.", {"reason": S})
def request_callback(ctx: ToolContext, a: dict) -> dict:
    convo_service.request_callback(ctx.db, ctx.customer, a["reason"], source=ctx.channel)
    _set_outcome(ctx, "callback")
    return {"callback_requested": True}


@tool("end_call", "Hang up after saying goodbye, once the caller has nothing else.", {}, channels=("voice",))
def end_call(ctx: ToolContext, a: dict) -> dict:
    ctx.flags["end_call"] = True
    return {"ending": True}
