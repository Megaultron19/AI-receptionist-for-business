import pytest
from fastapi.testclient import TestClient

from app import phone
from app.db import Session
from app.main import app
from app.models import Call, Failure, Reservation

from .conftest import at, client, day

CALL = {"CallUUID": "call-1", "From": "919876500030", "To": "918000000000"}


@pytest.fixture
def lunchtime(monkeypatch):
    monkeypatch.setattr(phone, "now", lambda: at("13:00"))


def post(path, key="pk", **extra):
    return TestClient(app).post(f"/webhooks/plivo/{path}?key={key}", data={**CALL, **extra})


def test_wrong_key_refused():
    assert post("answer", key="nope").status_code == 403


def test_closed_message(monkeypatch):
    monkeypatch.setattr(phone, "now", lambda: at("03:00"))
    body = post("answer").text
    assert "closed right now. Please call later" in body and 'language="hi-IN"' in body and "<Hangup/>" in body


def test_booking_by_phone(wa, claude, lunchtime):
    body = post("answer").text
    assert "<GetInput" in body and 'inputType="speech"' in body and "turn?key=pk" in body
    bot = claude([("book_table", {"date": str(day()), "time": "20:00", "guests": 2, "name": "Ravi", "notes": None})],
                 "Done. Your booking is confirmed for 8 PM.")
    body = post("turn", Speech="book a table for two at 8 pm, name Ravi").text
    assert "Your booking is confirmed" in body and 'language="en-IN"' in body
    assert "phone call" in bot.requests[0]["system"]
    with Session() as db:
        r = db.query(Reservation).one()
        assert r.source == "phone" and r.phone == "+919876500030" and r.qr_hash
        assert db.get(Call, "call-1").outcome == "booked"
    post("hangup")
    calls = client().get("/api/calls").json()
    assert calls[0]["outcome"] == "booked" and calls[0]["transcript"][0] == {"who": "caller", "text": "book a table for two at 8 pm, name Ravi"}


def test_hindi_reply_switches_language(wa, claude, lunchtime):
    post("answer")
    claude("जी, बताइए कितने लोग?")
    body = post("turn", Speech="mujhe table book karna hai").text
    assert body.count('language="hi-IN"') == 2


def test_silence_then_hang_up(lunchtime):
    post("answer")
    assert "did not catch that" in post("turn", Speech="").text
    post("turn", Speech="")
    assert "<Hangup/>" in post("turn", Speech="").text


def test_transfer_to_staff(wa, claude, lunchtime):
    owner = client()
    settings = owner.get("/api/restaurant").json()
    assert owner.put("/api/restaurant", json={**settings, "staff_phone": "9876500099"}).json()["staff_phone"] == "+919876500099"
    post("answer")
    claude([("talk_to_staff", {"reason": "wants a manager"})], "Connecting you now.")
    body = post("turn", Speech="let me talk to the manager").text
    assert "<Dial><Number>919876500099</Number></Dial>" in body


def test_ai_failure_transfers_or_asks_callback(wa, monkeypatch, lunchtime):
    from app import agent

    def broken():
        raise RuntimeError("api down")
    monkeypatch.setattr(agent, "client", broken)
    post("answer")
    body = post("turn", Speech="hello").text
    assert "call you back" in body and "<Hangup/>" in body
    with Session() as db:
        assert db.query(Failure).one().kind == "call_ai"
        assert db.get(Call, "call-1").outcome == "needs callback"
