"""Transactional reservation engine.

Correctness rests on the table_allocations exclusion constraint, not on the availability checks below:
the checks pick good candidates fast, then every insert is re-validated by PostgreSQL inside a
savepoint. A concurrent booking for the same table makes our insert fail with 23P01 and we move on
to the next candidate. Nothing here is ever "confirmed" until the transaction commits.
"""
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import Conflict, DomainError, NotFound
from ..core.events import alert, audit, usage
from ..core.jobs import cancel_jobs, enqueue
from ..customers.models import Customer
from ..db import utcnow
from ..restaurant.models import RestaurantSettings
from ..restaurant.service import duration_for, get_restaurant, is_open_between, open_intervals, tz
from ..tables.models import DiningTable, TableAllocation, TableCombination
from .models import ACTIVE_STATUSES, Reservation, WaitlistEntry

REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L: readable over the phone
EXCLUSION_VIOLATION = "23P01"

TRANSITIONS: dict[str, set[str]] = {
    "held": {"confirmed", "cancelled"},
    "confirmed": {"arrived", "seated", "cancelled", "no_show"},
    "arrived": {"seated", "completed", "no_show"},
    "seated": {"completed"},
    "no_show": {"arrived"},  # guest turned up late after all
    "completed": set(),
    "cancelled": set(),
}
RELEASING = {"completed", "cancelled", "no_show"}

Actor = tuple[str, object]


@dataclass(frozen=True)
class Option:
    table_ids: tuple[int, ...]
    label: str
    capacity: int


def new_ref(prefix: str) -> str:
    return prefix + "".join(secrets.choice(REF_ALPHABET) for _ in range(6))


def table_options(db: Session, party: int) -> list[Option]:
    """Single tables and allowed combinations that seat `party`, least wasted seats first."""
    opts = [Option((t.id,), t.code, t.capacity)
            for t in db.scalars(select(DiningTable).where(DiningTable.active))
            if t.min_capacity <= party <= t.capacity]
    for c in db.scalars(select(TableCombination).where(TableCombination.active)):
        if c.min_capacity <= party <= c.capacity and c.tables and all(t.active for t in c.tables):
            opts.append(Option(tuple(t.id for t in c.tables), c.name, c.capacity))
    return sorted(opts, key=lambda o: (o.capacity - party, len(o.table_ids), o.label))


def busy_periods(db: Session, start: datetime, end: datetime) -> dict[int, list[tuple[datetime, datetime]]]:
    busy: dict[int, list[tuple[datetime, datetime]]] = {}
    rows = db.execute(select(TableAllocation.table_id, TableAllocation.period).where(
        TableAllocation.active, TableAllocation.period.overlaps(Range(start, end, bounds="[)"))))
    for table_id, period in rows:
        busy.setdefault(table_id, []).append((period.lower, period.upper))
    return busy


def is_free(busy: dict[int, list[tuple[datetime, datetime]]], opt: Option, start: datetime, until: datetime) -> bool:
    return all(not (lo < until and start < hi) for tid in opt.table_ids for lo, hi in busy.get(tid, []))


def validate_request(db: Session, r: RestaurantSettings, party: int, start: datetime, *, staff: bool) -> tuple[datetime, datetime]:
    """Check booking rules. Returns (end, end+buffer). Staff bookings may skip notice/advance/party-size
    limits but never opening hours or table capacity."""
    if start.tzinfo is None:
        raise DomainError("Reservation time must include a timezone.")
    if not staff and not r.reservations_enabled:
        raise DomainError("We're not taking reservations right now.")
    if party < 1:
        raise DomainError("Party size must be at least 1.")
    if not staff and not (r.min_party <= party <= r.max_party):
        raise DomainError(f"We can book parties of {r.min_party} to {r.max_party} guests. For larger groups please speak to our staff.")
    local = start.astimezone(tz(r))
    if local.second or local.microsecond or (local.hour * 60 + local.minute) % r.slot_interval_minutes:
        raise DomainError(f"Please choose a time on a {r.slot_interval_minutes}-minute slot.")
    now = utcnow()
    if start <= now:
        raise DomainError("That time has already passed.")
    if not staff and start < now + timedelta(minutes=r.min_notice_minutes):
        raise DomainError(f"Bookings need at least {r.min_notice_minutes} minutes' notice.")
    if not staff and start > now + timedelta(days=r.max_advance_days):
        raise DomainError(f"We take bookings up to {r.max_advance_days} days ahead.")
    end = start + timedelta(minutes=duration_for(r, party))
    if not is_open_between(db, r, start, end):
        raise DomainError("The restaurant isn't open for a full sitting at that time.")
    return end, end + timedelta(minutes=r.buffer_minutes)


def available_times(db: Session, party: int, day: date, *, staff: bool = False) -> list[datetime]:
    """Start times on `day` (local) where some table or combination can seat `party`."""
    r = get_restaurant(db)
    intervals = open_intervals(db, r, day)
    opts = table_options(db, party)
    if not intervals or not opts:
        return []
    busy = busy_periods(db, intervals[0][0], max(e for _, e in intervals) + timedelta(hours=12))
    step, out = timedelta(minutes=r.slot_interval_minutes), []
    for s, e in intervals:
        local = s.astimezone(tz(r))
        offset = (local.hour * 60 + local.minute) % r.slot_interval_minutes
        t = s + timedelta(minutes=(r.slot_interval_minutes - offset) % r.slot_interval_minutes)
        while t < e:
            try:
                _, until = validate_request(db, r, party, t, staff=staff)
            except DomainError:
                t += step
                continue
            if any(is_free(busy, o, t, until) for o in opts):
                out.append(t)
            t += step
    return out


def suggest_alternatives(db: Session, party: int, wanted: datetime, *, limit: int = 4, staff: bool = False) -> list[datetime]:
    r = get_restaurant(db)
    day = wanted.astimezone(tz(r)).date()
    same_day = sorted(available_times(db, party, day, staff=staff), key=lambda t: abs(t - wanted))[:limit]
    if same_day:
        return sorted(same_day)
    for delta in (1, 2, 3):  # same time on the following days
        times = available_times(db, party, day + timedelta(days=delta), staff=staff)
        target = wanted + timedelta(days=delta)
        if times:
            return sorted(sorted(times, key=lambda t: abs(t - target))[:limit])
    return []


def _manual_option(db: Session, table_ids: list[int], party: int) -> Option:
    tables = list(db.scalars(select(DiningTable).where(DiningTable.id.in_(table_ids))))
    if len(tables) != len(set(table_ids)) or not all(t.active for t in tables):
        raise DomainError("One of the chosen tables doesn't exist or is inactive.")
    cap = sum(t.capacity for t in tables)
    if cap < party:
        raise DomainError(f"Those tables seat {cap}, fewer than {party} guests.")
    return Option(tuple(sorted(t.id for t in tables)), "+".join(t.code for t in tables), cap)


def _allocate(db: Session, res: Reservation, opts: list[Option], start: datetime, until: datetime) -> Option | None:
    """Try candidates in order; the database rejects any overlap. Returns the option that stuck."""
    busy = busy_periods(db, start, until)
    for opt in opts:
        if not is_free(busy, opt, start, until):
            continue
        try:
            with db.begin_nested():
                for tid in opt.table_ids:
                    db.add(TableAllocation(table_id=tid, reservation_id=res.id, period=Range(start, until, bounds="[)"), active=True))
                db.flush()
            return opt
        except IntegrityError as e:
            if getattr(e.orig, "sqlstate", None) != EXCLUSION_VIOLATION:
                raise
            # Someone else took this table between our check and insert; try the next candidate.
    return None


def _release(db: Session, res: Reservation) -> None:
    for a in res.allocations:
        a.active = False


def deposit_for(r: RestaurantSettings, party: int) -> int:
    if r.deposit_min_party and r.deposit_per_guest_paise and party >= r.deposit_min_party:
        return party * r.deposit_per_guest_paise
    return 0


def create_reservation(db: Session, *, customer: Customer, party: int, start: datetime, source: str, actor: Actor,
                       notes: str = "", staff: bool = False, table_ids: list[int] | None = None,
                       hold: str | None = None) -> Reservation:
    r = get_restaurant(db)
    end, until = validate_request(db, r, party, start, staff=staff)
    opts = [_manual_option(db, table_ids, party)] if table_ids else table_options(db, party)
    if not opts:
        raise DomainError(f"We don't have tables for a party of {party}.")
    deposit = deposit_for(r, party)
    hold_reason = hold or ("deposit" if deposit else None)
    with db.begin_nested():
        res = Reservation(ref=new_ref("R"), customer_id=customer.id, party_size=party, starts_at=start, ends_at=end,
                          source=source, notes=notes.strip()[:1000], deposit_paise=deposit,
                          status="held" if hold_reason else "confirmed", hold_reason=hold_reason,
                          hold_expires_at=utcnow() + timedelta(minutes=r.hold_minutes) if hold_reason else None,
                          confirmed_at=None if hold_reason else utcnow())
        db.add(res)
        db.flush()
        if not _allocate(db, res, opts, start, until):
            raise Conflict("No table is free for that time.")
    db.refresh(res)
    audit(db, "reservation.created", "reservation", res.ref, actor=actor, status=res.status, party=party,
          start=start.isoformat(), source=source, tables=[a.table_id for a in res.allocations])
    usage(db, "reservation_created", source=source)
    _after_status_change(db, r, res, None)
    return res


def get_by_ref(db: Session, ref: str, *, for_update: bool = False) -> Reservation:
    q = select(Reservation).where(Reservation.ref == ref.strip().upper())
    if for_update:
        q = q.with_for_update(of=Reservation)
    res = db.scalar(q)
    if not res:
        raise NotFound("Reservation")
    return res


def transition(db: Session, res: Reservation, new: str, *, actor: Actor, reason: str = "") -> Reservation:
    if new not in TRANSITIONS.get(res.status, set()):
        raise DomainError(f"A {res.status.replace('_', ' ')} reservation can't be marked {new.replace('_', ' ')}.")
    old, now = res.status, utcnow()
    res.status = new
    if new == "confirmed":
        res.confirmed_at, res.hold_reason, res.hold_expires_at = now, None, None
    elif new == "arrived":
        res.arrived_at = now
    elif new == "seated":
        res.seated_at = now
        res.arrived_at = res.arrived_at or now
    elif new == "completed":
        res.completed_at = now
    elif new == "cancelled":
        res.cancelled_at, res.cancel_reason = now, reason[:200]
    if new in RELEASING:
        _release(db, res)
    elif old == "no_show" and new == "arrived":
        # Re-take the tables only if they are still free; otherwise staff seat the guest manually.
        _reallocate_same(db, res)
    audit(db, f"reservation.{new}", "reservation", res.ref, actor=actor, previous=old, reason=reason or None)
    _after_status_change(db, get_restaurant(db), res, old)
    return res


def _reallocate_same(db: Session, res: Reservation) -> None:
    r = get_restaurant(db)
    until = res.ends_at + timedelta(minutes=r.buffer_minutes)
    tables = tuple(sorted({a.table_id for a in res.allocations}))
    for a in res.allocations:
        db.delete(a)
    db.flush()
    if not _allocate(db, res, [Option(tables, "same", 0)], res.starts_at, until):
        alert(db, "table_conflict", f"Late guest for {res.ref} arrived but their table is now taken; seat them manually.",
              severity="warning", ref=("reservation", res.ref))
    db.refresh(res)


def reschedule(db: Session, res: Reservation, *, start: datetime, party: int, actor: Actor, staff: bool = False,
               table_ids: list[int] | None = None) -> Reservation:
    if res.status not in ("held", "confirmed"):
        raise DomainError(f"A {res.status} reservation can't be changed.")
    r = get_restaurant(db)
    if not staff and res.starts_at - utcnow() < timedelta(minutes=r.cancellation_cutoff_minutes):
        raise DomainError("It's too close to the booking time to change it. Please call the restaurant.")
    end, until = validate_request(db, r, party, start, staff=staff)
    opts = [_manual_option(db, table_ids, party)] if table_ids else table_options(db, party)
    old = (res.starts_at.isoformat(), res.party_size, sorted(a.table_id for a in res.allocations))
    with db.begin_nested():
        for a in res.allocations:
            db.delete(a)  # frees the current tables inside the savepoint so the booking can keep them
        db.flush()
        res.starts_at, res.ends_at, res.party_size = start, end, party
        if not _allocate(db, res, opts, start, until):
            raise Conflict("No table is free for the new time.")
    db.refresh(res)
    # ponytail: a confirmed booking that grows past the deposit threshold isn't asked for a new deposit.
    audit(db, "reservation.rescheduled", "reservation", res.ref, actor=actor, previous=old,
          start=start.isoformat(), party=party, tables=[a.table_id for a in res.allocations])
    cancel_jobs(db, f"reminder:res:{res.id}:")
    cancel_jobs(db, f"noshow:res:{res.id}:")
    _after_status_change(db, r, res, res.status, rescheduled=True)
    return res


def customer_cancel(db: Session, res: Reservation, *, actor: Actor) -> Reservation:
    r = get_restaurant(db)
    if res.status == "confirmed" and res.starts_at - utcnow() < timedelta(minutes=r.cancellation_cutoff_minutes):
        raise DomainError(f"Bookings can only be cancelled up to {r.cancellation_cutoff_minutes} minutes before. "
                          "Please call the restaurant.")
    return transition(db, res, "cancelled", actor=actor, reason="cancelled by customer")


def _after_status_change(db: Session, r: RestaurantSettings, res: Reservation, old: str | None, *, rescheduled: bool = False) -> None:
    """Queue the side effects of a lifecycle change in the same transaction (transactional outbox)."""
    key = f"{res.id}:{res.status}:{int(res.starts_at.timestamp())}"
    if res.status == "held" and old is None:
        enqueue(db, "reservation.hold_expire", {"id": res.id}, run_at=res.hold_expires_at, dedupe_key=f"hold:res:{res.id}:{int(res.hold_expires_at.timestamp())}")
        if res.hold_reason == "deposit":
            enqueue(db, "payments.reservation_deposit", {"id": res.id}, dedupe_key=f"deposit:res:{res.id}")
        else:
            enqueue(db, "notify.reservation", {"id": res.id, "event": "waitlist_offer"}, dedupe_key=f"notify:res:{key}")
    if res.status == "confirmed" and (old != "confirmed" or rescheduled):
        enqueue(db, "notify.reservation", {"id": res.id, "event": "rescheduled" if rescheduled else "confirmed"},
                dedupe_key=f"notify:res:{key}:{'r' if rescheduled else 'c'}")
        ts = int(res.starts_at.timestamp())
        for offset in r.reminder_offsets_minutes or []:
            run_at = res.starts_at - timedelta(minutes=offset)
            if run_at > utcnow():
                enqueue(db, "reservation.reminder", {"id": res.id, "starts_at": ts}, run_at=run_at,
                        dedupe_key=f"reminder:res:{res.id}:{ts}:{offset}")
        enqueue(db, "reservation.no_show_check", {"id": res.id, "starts_at": ts},
                run_at=res.starts_at + timedelta(minutes=r.no_show_grace_minutes), dedupe_key=f"noshow:res:{res.id}:{ts}")
    if res.status in RELEASING and old in ACTIVE_STATUSES:
        cancel_jobs(db, f"reminder:res:{res.id}:")
        if res.status == "cancelled":
            cancel_jobs(db, f"noshow:res:{res.id}:")
            enqueue(db, "notify.reservation", {"id": res.id, "event": "cancelled"}, dedupe_key=f"notify:res:{res.id}:cancelled")
        # Freed tables may fit someone on the waitlist.
        day = res.starts_at.astimezone(tz(r)).date().isoformat()
        enqueue(db, "waitlist.process", {"day": day}, dedupe_key=f"waitlist:{day}:{res.id}:{res.status}")


# ---------- Holds, waitlist ----------

def confirm_hold(db: Session, res: Reservation, *, actor: Actor) -> Reservation:
    """Customer accepted a waitlist offer, or staff confirm a held booking."""
    if res.status != "held":
        raise DomainError("This booking isn't waiting for confirmation.")
    if res.hold_expires_at and res.hold_expires_at < utcnow() and actor[0] != "staff":
        raise DomainError("Sorry, that offer has expired.")
    entry = db.scalar(select(WaitlistEntry).where(WaitlistEntry.reservation_id == res.id))
    if entry:
        entry.status = "booked"
    if res.hold_reason == "waitlist" and res.deposit_paise and actor[0] != "staff":
        # Accepting a waitlist offer that needs a deposit: switch to a deposit hold.
        r = get_restaurant(db)
        res.hold_reason, res.hold_expires_at = "deposit", utcnow() + timedelta(minutes=r.hold_minutes)
        enqueue(db, "payments.reservation_deposit", {"id": res.id}, dedupe_key=f"deposit:res:{res.id}")
        enqueue(db, "reservation.hold_expire", {"id": res.id}, run_at=res.hold_expires_at,
                dedupe_key=f"hold:res:{res.id}:{int(res.hold_expires_at.timestamp())}")
        audit(db, "reservation.offer_accepted", "reservation", res.ref, actor=actor)
        return res
    return transition(db, res, "confirmed", actor=actor)


def expire_hold(db: Session, res: Reservation) -> None:
    if res.status != "held" or (res.hold_expires_at and res.hold_expires_at > utcnow()):
        return
    entry = db.scalar(select(WaitlistEntry).where(WaitlistEntry.reservation_id == res.id))
    if entry and entry.status == "offered":
        entry.status = "expired"
    transition(db, res, "cancelled", actor=("system", None), reason=f"{res.hold_reason or 'hold'} not completed in time")


def add_to_waitlist(db: Session, *, customer: Customer, party: int, earliest: datetime, latest: datetime, source: str,
                    actor: Actor, notes: str = "") -> WaitlistEntry:
    r = get_restaurant(db)
    if latest < earliest or latest <= utcnow():
        raise DomainError("Give a time window in the future.")
    if latest - earliest > timedelta(hours=12):
        raise DomainError("Waitlist windows can be at most 12 hours.")
    if party < 1 or party > max(r.max_party, 1):
        raise DomainError(f"Party size must be between 1 and {r.max_party}.")
    e = WaitlistEntry(customer_id=customer.id, day=earliest.astimezone(tz(r)).date(), earliest=earliest, latest=latest,
                      party_size=party, source=source, notes=notes[:500])
    db.add(e)
    db.flush()
    audit(db, "waitlist.added", "waitlist", e.id, actor=actor, party=party, earliest=earliest.isoformat())
    enqueue(db, "waitlist.process", {"day": e.day.isoformat()}, dedupe_key=f"waitlist:{e.day.isoformat()}:new:{e.id}")
    return e


def process_waitlist(db: Session, day: date) -> list[Reservation]:
    """Offer freed tables to waitlisted guests in order. Entries are row-locked (SKIP LOCKED) and every
    offer goes through the same exclusion-constrained allocation, so two guests can never be given the
    same released table."""
    offered = []
    entries = db.scalars(select(WaitlistEntry).where(WaitlistEntry.day == day, WaitlistEntry.status == "waiting")
                         .order_by(WaitlistEntry.created_at).with_for_update(skip_locked=True, of=WaitlistEntry)).all()
    for e in entries:
        if e.latest <= utcnow():
            e.status = "expired"
            continue
        times = [t for t in available_times(db, e.party_size, day) if e.earliest <= t <= e.latest]
        for t in times:
            try:
                res = create_reservation(db, customer=e.customer, party=e.party_size, start=t, source="waitlist",
                                         actor=("system", None), notes=e.notes, hold="waitlist")
            except (Conflict, DomainError):
                continue
            e.status, e.reservation_id = "offered", res.id
            offered.append(res)
            break
    return offered
