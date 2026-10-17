import json

import pytest

from fastapi.testclient import TestClient

from app.db import Session, now
from app.main import app
from app.models import Conversation, Failure, Reservation

from .conftest import at, client, day, whatsapp_post


@pytest.fixture
def codes(monkeypatch):
    from app import confirmations
    made, make = [], confirmations.segno.make
    monkeypatch.setattr(confirmations.segno, "make", lambda data, **kw: made.append(data) or make(data, **kw))
    return made


def test_webhook_verification_and_signature():
    c = TestClient(app)
    assert c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "42"}).text == "42"
    assert c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "42"}).status_code == 403
    assert c.post("/webhooks/whatsapp", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403


def test_booking_over_whatsapp_sends_reply_and_qr(wa, claude):
    bot = claude([("check_availability", {"date": str(day()), "guests": 2})],
                 [("book_table", {"date": str(day()), "time": "20:00", "guests": 2, "name": "Asha", "notes": None})],
                 "Booked! See you at 8.")
    c = TestClient(app)
    whatsapp_post(c, "table for 2 at 8pm", "m1")
    whatsapp_post(c, "table for 2 at 8pm", "m1")
    assert len(bot.requests) == 3
    tool_result = json.loads(bot.requests[1]["messages"][-1]["content"][0]["content"])
    assert "20:00" in tool_result["free_times"]
    with Session() as db:
        r = db.query(Reservation).one()
        assert r.source == "whatsapp" and r.phone == "+919876500001" and r.qr_hash
    kinds = [s[0] for s in wa.sent]
    assert kinds == ["text", "image"]
    assert wa.sent[0][2] == "Booked! See you at 8."
    assert r.ref in wa.sent[1][2] and "Guests: 2" in wa.sent[1][2] and "Table: T1" in wa.sent[1][2]


def test_full_slot_gives_alternatives(wa, claude):
    with Session() as db:
        from app.models import DiningTable
        for t in db.query(DiningTable):
            t.available = t.name == "T1"
        db.commit()
    owner = client()
    owner.post("/api/reservations", json={"name": "A", "phone": "9876500002", "guests": 2, "starts_at": at("20:00").isoformat()})
    bot = claude([("book_table", {"date": str(day()), "time": "20:00", "guests": 2, "name": "Asha", "notes": None})], "Sorry, 8 is full.")
    whatsapp_post(TestClient(app), "book 8pm for 2", "m2")
    result = json.loads(bot.requests[1]["messages"][-1]["content"][0]["content"])
    assert "No table is free" in result["error"] and "21:30" in result["error"]


def test_cannot_touch_other_peoples_bookings(wa, claude):
    owner = client()
    other = owner.post("/api/reservations", json={"name": "B", "phone": "9876500099", "guests": 2, "starts_at": at("19:00").isoformat()}).json()
    bot = claude([("cancel_booking", {"ref": other["ref"]})], "I can't find that booking.")
    whatsapp_post(TestClient(app), f"cancel {other['ref']}", "m3")
    assert "only find bookings made from this number" in bot.requests[1]["messages"][-1]["content"][0]["content"]
    with Session() as db:
        assert db.query(Reservation).one().status == "confirmed"


def test_ai_failure_hands_to_staff(wa, monkeypatch):
    from app import agent

    def broken():
        raise RuntimeError("api down")
    monkeypatch.setattr(agent, "client", broken)
    whatsapp_post(TestClient(app), "hello", "m4")
    assert "staff will reply" in wa.sent[0][2]
    with Session() as db:
        assert db.get(Conversation, "+919876500001").needs_staff
        assert db.query(Failure).one().kind == "ai_reply"
    whatsapp_post(TestClient(app), "hello again", "m5")
    assert len(wa.sent) == 1


def test_dashboard_booking_outside_24h_needs_template(wa, monkeypatch):
    owner = client()
    owner.post("/api/reservations", json={"name": "C", "phone": "9876500003", "guests": 2, "starts_at": at("19:00").isoformat()})
    with Session() as db:
        assert "no confirmation template" in db.query(Failure).one().detail
    from app import config as cfg
    monkeypatch.setattr(cfg.config(), "whatsapp_confirmation_template", "booking_confirmed")
    owner.post("/api/reservations", json={"name": "D", "phone": "9876500004", "guests": 2, "starts_at": at("19:00").isoformat()})
    kind, to, params = wa.sent[-1]
    assert kind == "template" and to == "+919876500004" and params[0] == "D" and params[4] == "2"


def test_qr_check_in(wa, codes):
    with Session() as db:
        db.merge(Conversation(phone="+919876500005", history=[], last_inbound_at=now()))
        db.commit()
    owner, door = client(), client("door", "door-pass-1")
    today_slot = owner.get(f"/api/reservations/availability?day={day(0)}&guests=2").json()
    if not today_slot:
        pytest.skip("no slots left today")
    hhmm = today_slot[0]
    r = owner.post("/api/reservations", json={"name": "E", "phone": "9876500005", "guests": 2, "starts_at": f"{day(0)}T{hhmm}:00"}).json()
    code = codes[-1]
    assert door.post("/api/checkin", json={"code": "RR:wrong"}).json() == {"ok": False, "message": "This QR code is not valid"}
    first = door.post("/api/checkin", json={"code": code}).json()
    assert first["ok"] and first["ref"] == r["ref"] and first["guests"] == 2
    again = door.post("/api/checkin", json={"code": code}).json()
    assert not again["ok"] and again["message"].startswith("Already checked in")


def test_reschedule_replaces_qr(wa, codes):
    with Session() as db:
        db.merge(Conversation(phone="+919876500006", history=[], last_inbound_at=now()))
        db.commit()
    owner = client()
    r = owner.post("/api/reservations", json={"name": "F", "phone": "9876500006", "guests": 2, "starts_at": at("19:00").isoformat()}).json()
    owner.put(f"/api/reservations/{r['ref']}", json={"guests": 2, "starts_at": at("20:00").isoformat()})
    assert owner.post("/api/checkin", json={"code": codes[0]}).json()["message"] == "This QR code is not valid"
    assert "for" in owner.post("/api/checkin", json={"code": codes[1]}).json()["message"]
