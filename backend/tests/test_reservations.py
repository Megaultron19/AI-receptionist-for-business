import threading
from datetime import timedelta

import pytest

from app.db import Session
from app.models import Block, DiningTable, Reservation
from app.reservations import BookingError, available_times, book, reschedule, restaurant, set_status

from .conftest import at, day


def reserve(db, guests, hhmm, phone="9876500001", offset=3):
    return book(db, name="Guest", phone=phone, guests=guests, start=at(hhmm, offset))


def test_picks_smallest_free_table(db):
    assert reserve(db, 2, "19:00").table.name == "T1"
    assert reserve(db, 2, "19:00").table.name == "T2"
    assert reserve(db, 2, "19:00").table.name == "T3"
    assert reserve(db, 5, "19:00").table.name == "T4"
    with pytest.raises(BookingError) as e:
        reserve(db, 2, "19:00")
    assert e.value.message == "No table is free at that time"
    assert at("20:30") in e.value.alternatives


def test_simultaneous_requests_never_share_a_table():
    with Session() as db:
        for t in db.query(DiningTable).filter(DiningTable.seats > 2):
            t.available = False
        db.commit()
    results, gate = [], threading.Barrier(15)

    def attempt(i):
        with Session() as db:
            gate.wait()
            try:
                results.append(book(db, name=f"G{i}", phone=f"98765{i:05d}", guests=2, start=at("20:00")).table_id)
            except BookingError:
                results.append(None)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(15)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    won = [r for r in results if r]
    assert sorted(won) == [1, 2]
    with Session() as db:
        assert db.query(Reservation).count() == 2


def test_overlap_uses_dining_length(db):
    for t in db.query(DiningTable).filter(DiningTable.name != "T1"):
        t.available = False
    db.commit()
    reserve(db, 2, "19:00")
    with pytest.raises(BookingError):
        reserve(db, 2, "20:00")
    assert reserve(db, 2, "20:30").table.name == "T1"


def test_opening_hours_and_rules(db):
    with pytest.raises(BookingError, match="not open"):
        reserve(db, 2, "22:00")
    with pytest.raises(BookingError, match="not open"):
        reserve(db, 2, "19:15")
    with pytest.raises(BookingError, match="1 to 12 guests"):
        reserve(db, 13, "19:00")
    with pytest.raises(BookingError, match="days ahead"):
        reserve(db, 2, "19:00", offset=40)
    with pytest.raises(BookingError, match="valid phone"):
        reserve(db, 2, "19:00", phone="12")
    r = restaurant(db)
    r.hours = {d: [["18:00", "01:00"]] for d in r.hours}
    db.commit()
    late = reserve(db, 2, "23:30")
    assert late.ends_at == at("23:30") + timedelta(minutes=90)


def test_blocks_and_unavailable_tables(db):
    db.add(Block(table_id=None, starts_at=at("18:00"), ends_at=at("21:00"), reason="Private party"))
    db.commit()
    with pytest.raises(BookingError):
        reserve(db, 2, "19:00")
    assert available_times(db, 2, day())[0].strftime("%H:%M") == "12:00"
    db.query(Block).delete()
    db.add(Block(table_id=1, starts_at=at("18:00"), ends_at=at("21:00")))
    db.get(DiningTable, 2).available = False
    db.commit()
    assert reserve(db, 2, "19:00").table.name == "T3"


def test_reschedule_and_status(db):
    a = reserve(db, 2, "19:00")
    reschedule(db, a, guests=2, start=at("19:30"))
    assert a.table.name == "T1"
    with pytest.raises(BookingError):
        set_status(db, a, "completed")
    set_status(db, a, "cancelled")
    assert reserve(db, 2, "19:30").table.name == "T1"
    with pytest.raises(BookingError, match="Only confirmed"):
        reschedule(db, a, guests=2, start=at("20:00"))
