"""Usage metering, reports, data export/anonymisation and configuration export/import (no secrets)."""
from datetime import timedelta
from typing import Any

from sqlalchemy import Text, cast, func, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..conversations.models import Conversation, Message
from ..core.errors import DomainError
from ..core.models import IntegrationStatus, Job, UsageEvent, WebhookEvent, WorkerHeartbeat
from ..customers.models import Customer
from ..db import utcnow
from ..menu.models import Addon, AddonGroup, ItemVariant, MenuCategory, MenuItem
from ..orders.models import Order
from ..payments.models import Payment
from ..reservations.models import Reservation
from ..restaurant.models import RestaurantSettings, SpecialDay
from ..restaurant.schemas import SettingsIn
from ..restaurant.service import get_restaurant
from ..tables.models import DiningTable, TableCombination

CONFIG_VERSION = 1


def usage_summary(db: Session, days: int) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(select(UsageEvent.kind, func.sum(UsageEvent.quantity), func.sum(UsageEvent.cost_paise), func.count())
                      .where(UsageEvent.created_at >= since).group_by(UsageEvent.kind)).all()
    totals = {k: {"quantity": int(q or 0), "cost_paise": int(c or 0), "events": n} for k, q, c, n in rows}
    daily = db.execute(select(func.date_trunc("day", UsageEvent.created_at).label("d"), UsageEvent.kind, func.sum(UsageEvent.quantity))
                       .where(UsageEvent.created_at >= since).group_by("d", UsageEvent.kind).order_by("d")).all()
    series: dict[str, dict[str, int]] = {}
    for d, kind, q in daily:
        series.setdefault(d.date().isoformat(), {})[kind] = int(q or 0)
    return {"days": days, "totals": totals, "daily": series,
            "estimated_cost_paise": sum(t["cost_paise"] for t in totals.values()),
            "note": "Costs are estimates from the unit rates in the environment; check provider invoices for actual charges."}


def health(db: Session) -> dict[str, Any]:
    s = get_settings()
    configured = {
        "llm": bool(s.anthropic_api_key), "whatsapp": bool(s.meta_access_token and s.meta_phone_number_id and s.meta_app_secret),
        "razorpay": bool(s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_webhook_secret),
        "plivo": bool(s.plivo_auth_token), "twilio": bool(s.twilio_auth_token),
    }
    status = {i.name: {"last_success_at": i.last_success_at, "last_failure_at": i.last_failure_at, "last_error": i.last_error,
                       "consecutive_failures": i.consecutive_failures} for i in db.scalars(select(IntegrationStatus))}
    beat = db.scalar(select(func.max(WorkerHeartbeat.beat_at)))
    jobs = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    overdue = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued", Job.run_at < utcnow() - timedelta(minutes=5)))
    hooks = dict(db.execute(select(WebhookEvent.status, func.count()).where(WebhookEvent.received_at > utcnow() - timedelta(days=1))
                            .group_by(WebhookEvent.status)).all())
    return {"integrations": {name: {"configured": ok, **status.get(name, {})} for name, ok in configured.items()},
            "worker": {"last_heartbeat": beat, "alive": bool(beat and utcnow() - beat < timedelta(minutes=2))},
            "jobs": {"by_status": jobs, "overdue": overdue}, "webhooks_24h": hooks}


def report(db: Session, start, end) -> dict[str, Any]:
    res = dict(db.execute(select(Reservation.status, func.count()).where(Reservation.starts_at >= start, Reservation.starts_at < end)
                          .group_by(Reservation.status)).all())
    covers = db.scalar(select(func.coalesce(func.sum(Reservation.party_size), 0)).where(
        Reservation.starts_at >= start, Reservation.starts_at < end, Reservation.status.in_(("arrived", "seated", "completed"))))
    by_source = dict(db.execute(select(Reservation.source, func.count()).where(Reservation.starts_at >= start, Reservation.starts_at < end)
                                .group_by(Reservation.source)).all())
    orders = dict(db.execute(select(Order.status, func.count()).where(Order.created_at >= start, Order.created_at < end)
                             .group_by(Order.status)).all())
    sales = db.scalar(select(func.coalesce(func.sum(Order.total_paise), 0)).where(
        Order.created_at >= start, Order.created_at < end, Order.status.in_(("submitted", "accepted", "preparing", "ready", "completed"))))
    paid = db.scalar(select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
        Payment.paid_at >= start, Payment.paid_at < end))
    refunded = db.scalar(select(func.coalesce(func.sum(Payment.refunded_paise), 0)).where(Payment.paid_at >= start, Payment.paid_at < end))
    return {"reservations_by_status": res, "reservations_by_source": by_source, "covers": int(covers or 0),
            "no_shows": res.get("no_show", 0), "orders_by_status": orders, "order_sales_paise": int(sales or 0),
            "payments_received_paise": int(paid or 0), "refunded_paise": int(refunded or 0)}



def export_customer(db: Session, c: Customer) -> dict[str, Any]:
    def rows(model, *cols):
        return [{col: getattr(x, col) for col in cols} for x in db.scalars(select(model).where(model.customer_id == c.id))]
    return {
        "customer": {k: getattr(c, k) for k in ("phone", "name", "language", "whatsapp_opt_in", "whatsapp_opt_in_at",
                                                "whatsapp_opt_in_source", "created_at")},
        "reservations": rows(Reservation, "ref", "status", "party_size", "starts_at", "notes", "created_at"),
        "orders": [{"ref": o.ref, "status": o.status, "total_paise": o.total_paise, "created_at": o.created_at,
                    "items": [f"{l.quantity} x {l.item_name}" for l in o.items]}
                   for o in db.scalars(select(Order).where(Order.customer_id == c.id))],
        "messages": rows(Message, "direction", "sender", "body", "created_at"),
    }


def anonymize_customer(db: Session, c: Customer) -> None:
    """Right to erasure: remove personal data but keep bookings/orders/payments as anonymous records
    (needed for accounts and GST). Payment provider records must be handled in Razorpay separately."""
    if any(r.status in ("held", "confirmed") for r in db.scalars(select(Reservation).where(Reservation.customer_id == c.id))):
        raise DomainError("Cancel this customer's upcoming bookings first.")
    c.phone, c.name = f"+0{c.id:014d}"[:16], ""
    c.whatsapp_opt_in, c.anonymized_at, c.last_inbound_whatsapp_at = False, utcnow(), None
    db.execute(update(Message).where(Message.customer_id == c.id).values(body="[deleted]"))
    db.execute(update(Conversation).where(Conversation.customer_id == c.id).values(transcript=[], state={}))
    db.execute(update(Reservation).where(Reservation.customer_id == c.id).values(notes="", staff_notes=""))
    db.execute(update(Order).where(Order.customer_id == c.id).values(special_instructions="", customer_gstin=""))


def purge_old_data(db: Session) -> dict[str, int]:
    r = get_restaurant(db)
    cutoff = utcnow() - timedelta(days=r.transcript_retention_days)
    n1 = db.execute(update(Conversation).where(Conversation.last_message_at < cutoff, func.json_array_length(Conversation.transcript) > 0)
                    .values(transcript=[], state={})).rowcount
    n2 = db.execute(update(Message).where(Message.created_at < cutoff, Message.body != "[expired]").values(body="[expired]")).rowcount
    n3 = db.execute(update(WebhookEvent).where(WebhookEvent.received_at < utcnow() - timedelta(days=90), cast(WebhookEvent.payload, Text) != "{}")
                    .values(payload={})).rowcount
    n4 = db.execute(Job.__table__.delete().where(Job.status.in_(("done", "cancelled")), Job.finished_at < utcnow() - timedelta(days=30))).rowcount
    return {"transcripts": n1, "messages": n2, "webhook_payloads": n3, "jobs": n4}



SECRETLESS_SKIP = {"id", "updated_at", "next_invoice_number"}


def export_config(db: Session) -> dict[str, Any]:
    r = get_restaurant(db)
    tables = db.scalars(select(DiningTable).order_by(DiningTable.sort)).all()
    return {
        "version": CONFIG_VERSION, "exported_at": utcnow().isoformat(),
        "settings": {c.name: getattr(r, c.name) for c in RestaurantSettings.__table__.columns if c.name not in SECRETLESS_SKIP},
        "special_days": [{"day": s.day.isoformat(), "closed": s.closed, "intervals": s.intervals, "note": s.note}
                         for s in db.scalars(select(SpecialDay))],
        "tables": [{k: getattr(t, k) for k in ("code", "name", "area", "capacity", "min_capacity", "active", "sort")} for t in tables],
        "combinations": [{"name": c.name, "capacity": c.capacity, "min_capacity": c.min_capacity, "active": c.active,
                          "tables": [t.code for t in c.tables]} for c in db.scalars(select(TableCombination))],
        "menu": [{"name": cat.name, "name_hi": cat.name_hi, "sort": cat.sort, "active": cat.active, "items": [
            {k: getattr(i, k) for k in ("name", "name_hi", "aliases", "description", "price_paise", "image_url", "dietary", "allergens",
                                        "spice_level", "available", "prep_minutes", "tax_rate_bp", "sort")} |
            {"variants": [{"name": v.name, "price_paise": v.price_paise, "available": v.available} for v in i.variants],
             "addon_groups": [{"name": g.name, "min_select": g.min_select, "max_select": g.max_select,
                               "addons": [{"name": a.name, "price_paise": a.price_paise, "available": a.available} for a in g.addons]}
                              for g in i.addon_groups]}
            for i in db.scalars(select(MenuItem).where(MenuItem.category_id == cat.id, MenuItem.active).order_by(MenuItem.sort))]}
            for cat in db.scalars(select(MenuCategory).order_by(MenuCategory.sort))],
    }


def import_config(db: Session, data: dict[str, Any], *, replace_menu: bool = False) -> dict[str, int]:
    """Apply an exported configuration. Settings are validated like a dashboard edit; tables are upserted
    by code; the menu is added (or replaced when replace_menu and nothing references it)."""
    if data.get("version") != CONFIG_VERSION:
        raise DomainError(f"Unsupported config version {data.get('version')}; expected {CONFIG_VERSION}.")
    settings = SettingsIn.model_validate({k: v for k, v in data.get("settings", {}).items() if k in SettingsIn.model_fields})
    r = get_restaurant(db, for_update=True)
    for k, v in settings.model_dump(exclude_unset=True, mode="json").items():
        setattr(r, k, v)
    from datetime import date
    for sd in data.get("special_days", []):
        row = db.scalar(select(SpecialDay).where(SpecialDay.day == date.fromisoformat(sd["day"]))) or SpecialDay(day=date.fromisoformat(sd["day"]))
        row.closed, row.intervals, row.note = sd["closed"], sd["intervals"], sd.get("note", "")
        db.add(row)
    by_code = {t.code: t for t in db.scalars(select(DiningTable))}
    for t in data.get("tables", []):
        row = by_code.get(t["code"]) or DiningTable(code=t["code"], capacity=t["capacity"])
        for k, v in t.items():
            setattr(row, k, v)
        db.add(row)
        by_code[t["code"]] = row
    db.flush()
    for c in data.get("combinations", []):
        if not db.scalar(select(TableCombination).where(TableCombination.name == c["name"])):
            db.add(TableCombination(name=c["name"], capacity=c["capacity"], min_capacity=c.get("min_capacity", 1),
                                    active=c.get("active", True), tables=[by_code[x] for x in c["tables"]]))
    items = 0
    if replace_menu:
        db.execute(update(MenuItem).values(active=False))
    for cat in data.get("menu", []):
        mc = db.scalar(select(MenuCategory).where(MenuCategory.name == cat["name"])) or MenuCategory(name=cat["name"])
        mc.name_hi, mc.sort, mc.active = cat.get("name_hi", ""), cat.get("sort", 0), cat.get("active", True)
        db.add(mc)
        db.flush()
        for it in cat.get("items", []):
            fields = {k: v for k, v in it.items() if k not in ("variants", "addon_groups")}
            item = MenuItem(category_id=mc.id, **fields,
                            variants=[ItemVariant(sort=i, **v) for i, v in enumerate(it.get("variants", []))],
                            addon_groups=[AddonGroup(sort=i, name=g["name"], min_select=g["min_select"], max_select=g["max_select"],
                                                     addons=[Addon(sort=j, **a) for j, a in enumerate(g["addons"])])
                                          for i, g in enumerate(it.get("addon_groups", []))])
            db.add(item)
            items += 1
    return {"tables": len(data.get("tables", [])), "menu_items": items}
