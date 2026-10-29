from datetime import timedelta

from fastapi.testclient import TestClient

from app import jobs
from app.confirmations import send_reminders
from app.db import Session, now
from app.main import app
from app.models import Conversation, DiningTable, Failure, Reservation, WaitlistEntry
from app.waitlist import book_from_waitlist

from .conftest import at, client, day, whatsapp_post


def booking_in(hours, phone="9876500040", booked_days_ago=2):
    start = (now() + timedelta(hours=hours)).replace(minute=0, second=0)
    with Session() as db:
        r = Reservation(ref=f"R{phone[-5:]}", name="Asha", phone="+91" + phone, guests=2, starts_at=start,
                        ends_at=start + timedelta(minutes=90), created_at=now() - timedelta(days=booked_days_ago))
        db.add(r)
        db.commit()
        return r.id


def chatted(phone):
    with Session() as db:
        db.merge(Conversation(phone=phone, history=[], last_inbound_at=now()))
        db.commit()


def test_reminder_sent_once(wa):
    booking_in(2)
    chatted("+919876500040")
    send_reminders()
    send_reminders()
    reminders = [m for m in wa.sent if m[2].startswith("Reminder")]
    assert len(reminders) == 1 and "Booking R00040" in reminders[0][2]


def test_reminder_template_and_skips(wa, monkeypatch):
    from app.config import config
    booking_in(2, phone="9876500041")
    booking_in(2, phone="9876500042", booked_days_ago=0)
    booking_in(10, phone="9876500043")
    send_reminders()
    with Session() as db:
        assert "no reminder template" in db.query(Failure).one().detail
    monkeypatch.setattr(config(), "whatsapp_reminder_template", "table_reminder")
    booking_in(2, phone="9876500044")
    send_reminders()
    assert len(wa.sent) == 1 and wa.sent[0][0] == "template" and wa.sent[0][2][-1] == "R00044"


def test_waitlist_books_one_person_per_free_table(wa, claude):
    with Session() as db:
        for t in db.query(DiningTable):
            t.available = t.name == "T1"
        db.commit()
    owner = client()
    taken = owner.post("/api/reservations", json={"name": "A", "phone": "9876500050", "guests": 2, "starts_at": at("20:00").isoformat()}).json()
    claude([("join_waitlist", {"date": str(day()), "time": "20:00", "guests": 2, "name": "Asha"})], "You are on the waitlist.")
    whatsapp_post(TestClient(app), "put me on the waitlist for 8", "w1")
    claude([("join_waitlist", {"date": str(day()), "time": "20:00", "guests": 2, "name": "Ravi"})], "You are on the waitlist.")
    whatsapp_post(TestClient(app), "waitlist for 8 please", "w2", phone="919876500002", name="Ravi")
    assert len(owner.get("/api/waitlist").json()) == 2
    book_from_waitlist()
    assert len(owner.get("/api/waitlist").json()) == 2
    owner.post(f"/api/reservations/{taken['ref']}/status?status=cancelled")
    book_from_waitlist()
    book_from_waitlist()
    with Session() as db:
        booked = db.query(Reservation).filter(Reservation.source == "waitlist").all()
        assert [(r.name, r.phone, r.table.name) for r in booked] == [("Asha", "+919876500001", "T1")]
        assert [e.status for e in db.query(WaitlistEntry).order_by(WaitlistEntry.id)] == ["booked", "waiting"]
    asha = [m for m in wa.sent if m[1] == "+919876500001"]
    assert "booked it for you" in asha[-2][2] and asha[-1][0] == "image"
    assert not any("booked it for you" in m[2] for m in wa.sent if m[1] == "+919876500002")
    assert "booked from the waitlist" in owner.get("/api/inbox").json()["notices"][0]["text"]


def test_old_waitlist_entries_expire():
    with Session() as db:
        db.add(WaitlistEntry(name="Old", phone="+919876500060", guests=2, wanted_at=now() - timedelta(hours=1), status="waiting"))
        db.commit()
    book_from_waitlist()
    with Session() as db:
        assert db.query(WaitlistEntry).one().status == "expired"


def test_staff_takes_over_chat(wa, claude):
    owner = client()
    claude([("talk_to_staff", {"reason": "large party of 30"})], "")
    c = TestClient(app)
    whatsapp_post(c, "we are 30 people", "h1")
    assert "passed your message to our staff" in wa.sent[-1][2]
    whatsapp_post(c, "hello?", "h2")
    assert len(wa.sent) == 1
    box = owner.get("/api/inbox").json()
    assert owner.get("/api/inbox/count").json()["count"] == 2
    chat = box["chats"][0]
    assert chat["can_reply"] and chat["transcript"][-1] == {"who": "customer", "text": "hello?"}
    assert "large party of 30" in box["notices"][0]["text"]
    assert owner.post("/api/inbox/reply", json={"phone": chat["phone"], "text": "Yes we can host you"}).json() == {"ok": True}
    assert wa.sent[-1][2] == "Yes we can host you"
    owner.post("/api/inbox/seen")
    owner.post("/api/inbox/release", json={"phone": chat["phone"]})
    assert owner.get("/api/inbox/count").json()["count"] == 0
    bot = claude("Great, see you!")
    whatsapp_post(c, "thanks", "h3")
    assert wa.sent[-1][2] == "Great, see you!"
    sent_history = bot.requests[0]["messages"]
    assert all(set(m) == {"role", "content"} for m in sent_history)
    assert sent_history[-2]["content"][0]["text"] == "Yes we can host you"


def test_staff_reply_failure_is_reported(wa):
    chatted("+919876500070")
    wa.fail = True
    r = client().post("/api/inbox/reply", json={"phone": "+919876500070", "text": "hi"})
    assert r.status_code == 502 and "24 hours" in r.json()["detail"]


def test_background_job_errors_are_recorded(monkeypatch, wa):
    def broken():
        raise RuntimeError("boom")
    broken.__name__ = "send_reminders"
    monkeypatch.setattr(jobs, "send_reminders", broken)
    jobs.run_once()
    with Session() as db:
        assert db.query(Failure).one().detail == "send_reminders: boom"
