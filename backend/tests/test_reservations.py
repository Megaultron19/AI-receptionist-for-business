import threading
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, DomainError
from app.core.jobs import drain
from app.customers.service import get_or_create
from app.db import SessionLocal
from app.reservations import engine
from app.reservations.models import Reservation, WaitlistEntry
from app.restaurant.models import SpecialDay
from app.tables.models import DiningTable

from .conftest import at, future_day

SYS = ("system", None)


def book(db, party, start, phone="9876500001", **kw):
    c = get_or_create(db, phone, "Guest")
    res = engine.create_reservation(db, customer=c, party=party, start=start, source="whatsapp", actor=SYS, **kw)
    db.commit()
    return res


def tables_of(res):
    return sorted(a.table_id for a in res.allocations if a.active)


def test_smallest_fitting_table_then_next(db, restaurant):
    day = future_day()
    a = book(db, 2, at(day, "19:00"))
    b = book(db, 2, at(day, "19:00"), phone="9876500002")
    c = book(db, 2, at(day, "19:00"), phone="9876500003")
    assert tables_of(a) == [1] and tables_of(b) == [2] and tables_of(c) == [3]  # then the 4-top
    assert a.status == "confirmed" and a.ref.startswith("R")


def test_party_size_and_combinations(db, restaurant):
    day = future_day()
    big = book(db, 5, at(day, "19:00"))
    assert tables_of(big) == [4]  # only the 6-top seats 5
    four = book(db, 4, at(day, "19:00"), phone="9876500002")
    assert tables_of(four) == [3]
    combo = book(db, 4, at(day, "19:00"), phone="9876500003")
    assert tables_of(combo) == [1, 2]  # 4-top gone: tables T1+T2 pushed together
    with pytest.raises(Conflict):
        book(db, 4, at(day, "19:00"), phone="9876500004")
    with pytest.raises(DomainError, match="tables for a party of 7"):
        book(db, 7, at(day, "13:00"))


def test_buffer_and_overlap(db, restaurant):
    day = future_day()
    db.get(DiningTable, 2).active = False
    db.get(DiningTable, 3).active = False
    db.get(DiningTable, 4).active = False
    db.commit()
    book(db, 2, at(day, "19:00"))  # holds T1 until 20:30 + 15 min buffer
    with pytest.raises(Conflict):
        book(db, 2, at(day, "20:30"), phone="9876500002")
    assert tables_of(book(db, 2, at(day, "20:45"), phone="9876500003")) == [1]
    with pytest.raises(Conflict):
        book(db, 2, at(day, "18:00"), phone="9876500004")  # 18:00-19:45 overlaps 19:00


def test_concurrent_bookings_never_double_allocate(db, restaurant):
    """20 simultaneous requests (calls, WhatsApp, dashboard) for 2-person tables at the same time."""
    day = future_day()
    for t in (3, 4):
        db.get(DiningTable, t).active = False
    db.commit()
    start = at(day, "20:00")
    results, barrier = [], threading.Barrier(20)

    def attempt(i):
        with SessionLocal() as s:
            c = get_or_create(s, f"98765{i:05d}", f"G{i}")
            s.commit()
            barrier.wait()
            try:
                res = engine.create_reservation(s, customer=c, party=2, start=start, source="voice", actor=SYS)
                s.commit()
                results.append(tables_of(res))
            except Conflict:
                s.rollback()
                results.append(None)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    won = [r for r in results if r]
    # T1, T2 and the T1+T2 combination: only two bookings can ever fit.
    assert len(won) == 2 and sorted(won) == [[1], [2]]
    assert db.scalar(select(Reservation).where(Reservation.status == "confirmed").limit(1)) is not None
    assert len(db.scalars(select(Reservation)).all()) == 2  # failed attempts left nothing behind


def test_opening_hours_holidays_and_midnight(db, restaurant):
    day = future_day()
    with pytest.raises(DomainError, match="isn't open"):
        book(db, 2, at(day, "22:00"))  # 22:00 + 90 min runs past 23:00
    with pytest.raises(DomainError, match="isn't open"):
        book(db, 2, at(day, "11:00"))
    db.add(SpecialDay(day=day, closed=True, note="Diwali"))
    db.commit()
    with pytest.raises(DomainError, match="isn't open"):
        book(db, 2, at(day, "19:00"))
    assert engine.available_times(db, 2, day) == []
    # Late-night hours that run past midnight
    day2 = future_day(8)
    restaurant.opening_hours = {d: [["18:00", "01:30"]] for d in restaurant.opening_hours}
    db.commit()
    res = book(db, 2, at(day2, "23:45"))
    assert res.ends_at == at(day2, "23:45") + timedelta(minutes=90)


def test_rules_slot_notice_advance_and_party_limits(db, restaurant):
    day = future_day()
    with pytest.raises(DomainError, match="15-minute slot"):
        book(db, 2, at(day, "19:10"))
    with pytest.raises(DomainError, match="days ahead"):
        book(db, 2, at(future_day(60), "19:00"))
    with pytest.raises(DomainError, match="parties of 1 to 12"):
        book(db, 13, at(day, "19:00"))
    # Staff may book beyond the advance limit (but never outside hours)
    c = get_or_create(db, "9876500009")
    res = engine.create_reservation(db, customer=c, party=2, start=at(future_day(60), "19:00"), source="dashboard", actor=SYS, staff=True)
    assert res.status == "confirmed"


def test_blocked_table_is_skipped(db, owner, restaurant):
    day = future_day()
    for t in (2, 3, 4):
        db.get(DiningTable, t).active = False
    db.commit()
    r = owner.post("/api/tables/blocks", json={"table_ids": [1], "starts_at": f"{day}T18:00", "ends_at": f"{day}T22:00", "reason": "Private event"})
    assert r.status_code == 200, r.text
    with pytest.raises(Conflict):
        book(db, 2, at(day, "19:00"))
    owner.delete(f"/api/tables/blocks/{r.json()[0]['id']}")
    assert tables_of(book(db, 2, at(day, "19:00"))) == [1]
    # Blocking over an existing booking is refused
    r = owner.post("/api/tables/blocks", json={"table_ids": [1], "starts_at": f"{day}T19:30", "ends_at": f"{day}T20:00"})
    assert r.status_code == 409


def test_status_transitions_and_release(db, restaurant):
    day = future_day()
    res = book(db, 2, at(day, "19:00"))
    with pytest.raises(DomainError):
        engine.transition(db, res, "completed", actor=SYS)  # can't complete before seating
    engine.transition(db, res, "seated", actor=SYS)
    engine.transition(db, res, "completed", actor=SYS)
    db.commit()
    assert tables_of(res) == []  # table released early
    with pytest.raises(DomainError):
        engine.transition(db, res, "cancelled", actor=SYS)


def test_reschedule_moves_tables_or_fails_atomically(db, restaurant):
    day = future_day()
    for t in (3, 4):
        db.get(DiningTable, t).active = False
    db.commit()
    a = book(db, 2, at(day, "19:00"))                       # T1 19:00-20:45
    b = book(db, 2, at(day, "21:00"), phone="9876500002")   # T1 again (free from 20:45)
    assert tables_of(a) == tables_of(b) == [1]
    engine.reschedule(db, a, start=at(day, "19:30"), party=2, actor=SYS)
    db.commit()
    assert tables_of(a) == [2]  # would collide with b on T1, so it moved to T2
    book(db, 2, at(day, "17:00"), phone="9876500003")       # T1
    book(db, 2, at(day, "17:00"), phone="9876500004")       # T2
    with pytest.raises(Conflict):
        engine.reschedule(db, b, start=at(day, "17:30"), party=2, actor=SYS)
    db.rollback()
    db.refresh(b)
    assert b.starts_at == at(day, "21:00") and tables_of(b) == [1]  # untouched after the failed move


def test_cancellation_frees_table_and_waitlist_gets_one_offer(db, restaurant):
    day = future_day()
    for t in (2, 3, 4):
        db.get(DiningTable, t).active = False
    db.commit()
    res = book(db, 2, at(day, "19:00"))
    w1 = get_or_create(db, "9876511111", "Wait One")
    w2 = get_or_create(db, "9876522222", "Wait Two")
    e1 = engine.add_to_waitlist(db, customer=w1, party=2, earliest=at(day, "18:45"), latest=at(day, "19:30"), source="whatsapp", actor=SYS)
    e2 = engine.add_to_waitlist(db, customer=w2, party=2, earliest=at(day, "18:45"), latest=at(day, "19:30"), source="whatsapp", actor=SYS)
    db.commit()
    drain()
    db.refresh(e1)
    assert e1.status == "waiting"  # nothing free yet
    engine.customer_cancel(db, res, actor=("customer", res.customer_id))
    db.commit()
    drain()
    db.expire_all()
    e1, e2 = db.get(WaitlistEntry, e1.id), db.get(WaitlistEntry, e2.id)
    assert e1.status == "offered" and e2.status == "waiting"  # first come, first served; one table, one offer
    held = db.get(Reservation, e1.reservation_id)
    assert held.status == "held" and held.hold_reason == "waitlist" and tables_of(held) == [1]
    engine.confirm_hold(db, held, actor=("customer", w1.id))
    db.commit()
    assert held.status == "confirmed" and db.get(WaitlistEntry, e1.id).status == "booked"


def test_expired_waitlist_offer_moves_to_next_guest(db, restaurant):
    day = future_day()
    for t in (2, 3, 4):
        db.get(DiningTable, t).active = False
    db.commit()
    res = book(db, 2, at(day, "19:00"))
    w1, w2 = get_or_create(db, "9876511111"), get_or_create(db, "9876522222")
    e1 = engine.add_to_waitlist(db, customer=w1, party=2, earliest=at(day, "19:00"), latest=at(day, "19:00"), source="whatsapp", actor=SYS)
    e2 = engine.add_to_waitlist(db, customer=w2, party=2, earliest=at(day, "19:00"), latest=at(day, "19:00"), source="whatsapp", actor=SYS)
    engine.transition(db, res, "cancelled", actor=SYS)
    db.commit()
    drain()
    db.expire_all()
    held = db.get(Reservation, db.get(WaitlistEntry, e1.id).reservation_id)
    held.hold_expires_at = held.hold_expires_at - timedelta(hours=1)
    db.commit()
    engine.expire_hold(db, held)
    db.commit()
    drain()
    db.expire_all()
    assert db.get(WaitlistEntry, e1.id).status == "expired"
    assert db.get(WaitlistEntry, e2.id).status == "offered"


def test_reminders_scheduled_and_cancelled(db, restaurant):
    from app.core.models import Job
    res = book(db, 2, at(future_day(), "19:00"))
    jobs = {j.kind: j for j in db.scalars(select(Job).where(Job.payload["id"].as_integer() == res.id))}
    assert jobs["reservation.reminder"].status == "queued"
    assert jobs["reservation.reminder"].run_at == res.starts_at - timedelta(minutes=120)
    engine.transition(db, res, "cancelled", actor=SYS)
    db.commit()
    db.refresh(jobs["reservation.reminder"])
    assert jobs["reservation.reminder"].status == "cancelled"


def test_timeline_shows_bookings_and_blocks(db, owner, restaurant):
    day = future_day()
    res = book(db, 4, at(day, "19:30"))
    r = owner.post("/api/tables/blocks", json={"table_ids": [1], "starts_at": f"{day}T12:00", "ends_at": f"{day}T14:00", "reason": "Repair"})
    assert r.status_code == 200, r.text
    rows = {r["code"]: r["items"] for r in owner.get(f"/api/tables/timeline?day={day}").json()}
    assert rows["T3"][0]["ref"] == res.ref and rows["T3"][0]["party"] == 4 and rows["T3"][0]["name"] == "Guest"
    assert rows["T1"][0]["type"] == "block" and rows["T1"][0]["reason"] == "Repair"
