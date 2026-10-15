"""Order lifecycle: editable drafts, server-side bills, kitchen-capacity quotes and a strict state machine.
Payment confirmation (paid) and restaurant acceptance (accepted) are separate states."""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import DomainError, NotFound
from ..core.events import audit, usage
from ..core.jobs import enqueue
from ..customers.models import Customer
from ..db import utcnow
from ..menu.models import MenuItem
from ..reservations.engine import new_ref
from ..restaurant.models import RestaurantSettings
from ..restaurant.schemas import GSTIN
from ..restaurant.service import get_restaurant, is_open_between, tz
from .billing import Line, compute_bill, minimum_payment
from .models import Order, OrderItem

TRANSITIONS: dict[str, set[str]] = {
    "draft": {"awaiting_payment", "submitted", "cancelled"},
    "awaiting_payment": {"payment_pending", "paid", "draft", "cancelled"},
    "payment_pending": {"paid", "awaiting_payment", "cancelled"},
    "paid": {"submitted", "cancelled"},
    "submitted": {"accepted", "cancelled"},
    "accepted": {"preparing", "ready", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"completed"},
    "completed": {"refunded"},
    "cancelled": {"refunded"},
    "refunded": set(),
}
KITCHEN_ACTIVE = ("submitted", "accepted", "preparing")
EDITABLE = ("draft",)
MAX_QTY = 50
MAX_LINES = 40

Actor = tuple[str, object]


def get_order(db: Session, ref: str, *, for_update: bool = False) -> Order:
    q = select(Order).where(Order.ref == ref.strip().upper())
    if for_update:
        q = q.with_for_update(of=Order)
    o = db.scalar(q)
    if not o:
        raise NotFound("Order")
    return o


def create_draft(db: Session, *, customer: Customer, channel: str, actor: Actor, order_type: str = "pickup",
                 reservation_id: int | None = None) -> Order:
    r = get_restaurant(db)
    if not r.ordering_enabled:
        raise DomainError("We're not taking pre-orders right now.")
    if order_type not in ("pickup", "dine_in"):
        raise DomainError("Order type must be pickup or dine_in.")
    o = Order(ref=new_ref("F"), customer_id=customer.id, channel=channel, order_type=order_type,
              reservation_id=reservation_id, status="draft")
    db.add(o)
    db.flush()
    recalculate(db, o)
    audit(db, "order.created", "order", o.ref, actor=actor, channel=channel, order_type=order_type)
    return o


def _require_editable(o: Order) -> None:
    if o.status not in EDITABLE:
        raise DomainError("This order is already confirmed and can't be edited. Cancel it and start a new one.")


def _resolve(db: Session, item_id: int, variant_id: int | None, addon_ids: list[int]):
    """Validate a menu selection against current menu records. Returns (item, variant, addons, unit_price)."""
    it = db.get(MenuItem, item_id)
    if not it or not it.active:
        raise DomainError("That dish isn't on the menu.")
    if not it.available:
        raise DomainError(f"Sorry, {it.name} is not available right now.")
    variant = None
    if it.variants:
        if variant_id is None:
            raise DomainError(f"{it.name} comes in {', '.join(v.name for v in it.variants)}. Which one?")
        variant = next((v for v in it.variants if v.id == variant_id), None)
        if not variant:
            raise DomainError(f"Unknown option for {it.name}.")
        if not variant.available:
            raise DomainError(f"Sorry, {it.name} ({variant.name}) is not available right now.")
    elif variant_id is not None:
        raise DomainError(f"{it.name} has no size options.")
    chosen, all_addons = [], {a.id: (g, a) for g in it.addon_groups for a in g.addons}
    if len(set(addon_ids)) != len(addon_ids):
        raise DomainError("An add-on was chosen twice.")
    for aid in addon_ids:
        if aid not in all_addons:
            raise DomainError(f"That add-on isn't offered with {it.name}.")
        g, a = all_addons[aid]
        if not a.available:
            raise DomainError(f"Sorry, {a.name} is not available right now.")
        chosen.append((g, a))
    for g in it.addon_groups:
        n = sum(1 for cg, _ in chosen if cg.id == g.id)
        if n < g.min_select:
            raise DomainError(f"Please choose {g.min_select if g.min_select == g.max_select else f'at least {g.min_select}'} "
                              f"for '{g.name}' ({', '.join(a.name for a in g.addons if a.available)}).")
        if n > g.max_select:
            raise DomainError(f"You can choose at most {g.max_select} for '{g.name}'.")
    unit = (variant.price_paise if variant else it.price_paise) + sum(a.price_paise for _, a in chosen)
    return it, variant, [a for _, a in chosen], unit


def add_item(db: Session, o: Order, *, item_id: int, quantity: int, actor: Actor, variant_id: int | None = None,
             addon_ids: list[int] | None = None, instructions: str = "") -> OrderItem:
    _require_editable(o)
    if not 1 <= quantity <= MAX_QTY:
        raise DomainError(f"Quantity must be between 1 and {MAX_QTY}.")
    if len(o.items) >= MAX_LINES:
        raise DomainError("That's a very large order; please call the restaurant.")
    r = get_restaurant(db)
    it, variant, addons, unit = _resolve(db, item_id, variant_id, sorted(addon_ids or []))
    line = OrderItem(menu_item_id=it.id, variant_id=variant.id if variant else None, item_name=it.name,
                     variant_name=variant.name if variant else "", unit_price_paise=unit, quantity=quantity,
                     addons=[{"id": a.id, "name": a.name, "price_paise": a.price_paise} for a in addons],
                     instructions=instructions.strip()[:300], prep_minutes=it.prep_minutes,
                     tax_rate_bp=it.tax_rate_bp if it.tax_rate_bp is not None else r.default_tax_rate_bp)
    o.items.append(line)
    db.flush()
    recalculate(db, o)
    audit(db, "order.item_added", "order", o.ref, actor=actor, item=it.name, variant=line.variant_name, qty=quantity)
    return line


def update_item(db: Session, o: Order, line_id: int, *, actor: Actor, quantity: int | None = None,
                variant_id: int | None = None, addon_ids: list[int] | None = None, instructions: str | None = None) -> None:
    _require_editable(o)
    line = next((l for l in o.items if l.id == line_id), None)
    if not line:
        raise NotFound("Order line")
    if quantity is not None:
        if quantity == 0:
            return remove_item(db, o, line_id, actor=actor)
        if not 1 <= quantity <= MAX_QTY:
            raise DomainError(f"Quantity must be between 1 and {MAX_QTY}.")
        line.quantity = quantity
    if variant_id is not None or addon_ids is not None:
        r = get_restaurant(db)
        it, variant, addons, unit = _resolve(db, line.menu_item_id, variant_id if variant_id is not None else line.variant_id,
                                             sorted(addon_ids if addon_ids is not None else [a["id"] for a in line.addons]))
        line.variant_id, line.variant_name = (variant.id, variant.name) if variant else (None, "")
        line.addons = [{"id": a.id, "name": a.name, "price_paise": a.price_paise} for a in addons]
        line.unit_price_paise = unit
        line.tax_rate_bp = it.tax_rate_bp if it.tax_rate_bp is not None else r.default_tax_rate_bp
    if instructions is not None:
        line.instructions = instructions.strip()[:300]
    db.flush()
    recalculate(db, o)
    audit(db, "order.item_updated", "order", o.ref, actor=actor, line=line_id, qty=line.quantity)


def remove_item(db: Session, o: Order, line_id: int, *, actor: Actor) -> None:
    _require_editable(o)
    line = next((l for l in o.items if l.id == line_id), None)
    if not line:
        raise NotFound("Order line")
    o.items.remove(line)
    db.flush()
    recalculate(db, o)
    audit(db, "order.item_removed", "order", o.ref, actor=actor, item=line.item_name)


def recalculate(db: Session, o: Order, r: RestaurantSettings | None = None) -> None:
    r = r or get_restaurant(db)
    lines = [Line(name=l.item_name, quantity=l.quantity, unit_price_paise=l.unit_price_paise, tax_rate_bp=l.tax_rate_bp,
                  detail=", ".join(filter(None, [l.variant_name, *(a["name"] for a in l.addons), l.instructions])))
             for l in o.items]
    bill = compute_bill(lines, order_type=o.order_type, default_tax_bp=r.default_tax_rate_bp,
                        prices_include_tax=r.prices_include_tax, charges=r.charges or [], discounts=r.discounts or [])
    o.bill = bill.as_dict() | {"line_ids": [l.id for l in o.items]}
    o.subtotal_paise, o.discount_paise, o.tax_paise, o.total_paise = bill.subtotal, bill.discount, bill.tax_total, bill.total
    o.charges_paise = sum(c["amount"] for c in bill.charges)
    o.amount_due_paise = minimum_payment(bill.total, r.min_payment_type, r.min_payment_value)
    o.bill["amount_due_now"] = o.amount_due_paise


def kitchen_quote(db: Session, o: Order) -> dict:
    """Realistic preparation estimate from item prep times and the current kitchen queue. A quote, not a
    promise: the restaurant confirms the time when it accepts the order."""
    r = get_restaurant(db)
    active = db.scalars(select(Order).where(Order.status.in_(KITCHEN_ACTIVE), Order.id != o.id)).all()
    own = max((l.prep_minutes for l in o.items), default=0)
    queue_prep = sorted((max((l.prep_minutes for l in a.items), default=0) for a in active), reverse=True)
    waves = len(active) // max(r.kitchen_parallel_orders, 1)
    wait = sum(queue_prep[i * r.kitchen_parallel_orders] for i in range(waves)) if waves else 0
    estimate = own + wait
    reasons = []
    if any(l.prep_minutes > r.prep_target_minutes for l in o.items):
        reasons.append("some dishes take longer to prepare")
    if wait:
        reasons.append(f"the kitchen has {len(active)} orders in progress")
    return {"estimate_minutes": estimate, "target_minutes": r.prep_target_minutes,
            "meets_target": estimate <= r.prep_target_minutes, "kitchen_full": len(active) >= r.max_active_orders,
            "reasons": reasons}


def confirm(db: Session, o: Order, *, actor: Actor, scheduled_for: datetime | None = None, gstin: str = "") -> Order:
    """Customer confirmed the summary. Re-validates every line against the live menu and recomputes the bill."""
    _require_editable(o)
    r = get_restaurant(db)
    if not o.items:
        raise DomainError("The order is empty.")
    for l in o.items:
        _resolve(db, l.menu_item_id, l.variant_id, [a["id"] for a in l.addons])
    recalculate(db, o, r)
    quote = kitchen_quote(db, o)
    if quote["kitchen_full"]:
        raise DomainError("The kitchen is at full capacity right now. Please try again a little later or schedule for later.")
    now = utcnow()
    if scheduled_for:
        if scheduled_for < now + timedelta(minutes=quote["estimate_minutes"]):
            raise DomainError(f"The earliest we could have it ready is in about {quote['estimate_minutes']} minutes.")
        if scheduled_for > now + timedelta(days=r.max_advance_days or 1):
            raise DomainError("That's too far ahead.")
    ready_by = scheduled_for or now + timedelta(minutes=quote["estimate_minutes"])
    if not is_open_between(db, r, ready_by, ready_by):
        raise DomainError("The restaurant isn't open at that time.")
    if gstin:
        if not GSTIN.match(gstin.upper()):
            raise DomainError("That GSTIN doesn't look valid.")
        o.customer_gstin = gstin.upper()
    o.scheduled_for, o.estimate_minutes, o.confirmed_at = scheduled_for, quote["estimate_minutes"], now
    if o.amount_due_paise > 0:
        transition(db, o, "awaiting_payment", actor=actor)
        enqueue(db, "payments.order_link", {"order_id": o.id}, dedupe_key=f"paylink:order:{o.id}:{o.total_paise}:{int(now.timestamp())}")
    else:
        transition(db, o, "submitted", actor=actor)
    return o


def transition(db: Session, o: Order, new: str, *, actor: Actor, reason: str = "", eta_minutes: int | None = None) -> Order:
    if new not in TRANSITIONS.get(o.status, set()):
        raise DomainError(f"An order that is {o.status.replace('_', ' ')} can't be moved to {new.replace('_', ' ')}.")
    old, now = o.status, utcnow()
    r = get_restaurant(db)
    if new == "accepted":
        minutes = eta_minutes if eta_minutes is not None else kitchen_quote(db, o)["estimate_minutes"]
        if not 0 <= minutes <= 24 * 60:
            raise DomainError("Give a preparation time in minutes.")
        o.accepted_at = now
        earliest = now + timedelta(minutes=minutes)
        o.estimated_ready_at = max(earliest, o.scheduled_for) if o.scheduled_for else earliest
    o.status = new
    if new == "submitted":
        o.submitted_at = now
        if not o.invoice_number and (o.amount_paid_paise or o.total_paise):
            o.invoice_number = _next_invoice(db)
    elif new == "ready":
        o.ready_at = now
    elif new == "completed":
        o.completed_at = now
        usage(db, "order_completed", channel=o.channel, total_paise=o.total_paise)
    elif new == "cancelled":
        o.cancelled_at, o.cancel_reason = now, reason[:200]
    elif new == "draft":
        o.confirmed_at = None
    audit(db, f"order.{new}", "order", o.ref, actor=actor, previous=old, reason=reason or None, eta_minutes=eta_minutes)
    if new in ("accepted", "ready", "cancelled", "completed") or (new == "submitted" and old in ("paid", "draft")):
        enqueue(db, "notify.order", {"order_id": o.id, "event": new}, dedupe_key=f"notify:order:{o.id}:{new}")
    if new == "submitted":
        enqueue(db, "orders.kitchen_alert", {"order_id": o.id}, dedupe_key=f"kitchen:order:{o.id}")
        if r.auto_accept_orders and not kitchen_quote(db, o)["kitchen_full"]:
            transition(db, o, "accepted", actor=("system", None))
    if new == "cancelled" and o.amount_paid_paise > 0:
        enqueue(db, "payments.refund_order", {"order_id": o.id, "reason": reason or "order cancelled"},
                dedupe_key=f"refund:order:{o.id}")
    if new == "draft" and old == "awaiting_payment":
        enqueue(db, "payments.cancel_order_links", {"order_id": o.id}, dedupe_key=f"cancel-links:order:{o.id}:{int(now.timestamp())}")
    if new == "cancelled" and old in ("awaiting_payment", "payment_pending"):
        enqueue(db, "payments.cancel_order_links", {"order_id": o.id}, dedupe_key=f"cancel-links:order:{o.id}:cancel")
    return o


def reopen_for_edit(db: Session, o: Order, *, actor: Actor) -> Order:
    """Customer wants to change the order after the payment link was sent: back to draft, old link cancelled."""
    if o.status != "awaiting_payment":
        raise DomainError("Only an order that is waiting for payment can be edited again.")
    return transition(db, o, "draft", actor=actor)


def _next_invoice(db: Session) -> str:
    r = get_restaurant(db, for_update=True)
    n = r.next_invoice_number
    r.next_invoice_number = n + 1
    fy = _financial_year(utcnow().astimezone(tz(r)))
    return f"{r.invoice_prefix}/{fy}/{n:05d}"


def _financial_year(d: datetime) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def active_kitchen_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Order).where(Order.status.in_(KITCHEN_ACTIVE))) or 0
