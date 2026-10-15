import re
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.conversations.models import Conversation, Notification
from app.conversations.service import handoff
from app.core.jobs import drain
from app.core.models import Alert, Job
from app.customers.service import get_or_create
from app.db import utcnow
from app.main import app
from app.orders import service as orders
from app.qr.models import QrToken
from app.reservations import engine
from app.whatsapp.client import WhatsAppError

from .conftest import at, future_day, in_window

SYS = ("system", None)


def booked(db, phone="9876500001", start="19:00"):
    c = get_or_create(db, phone, "Asha")
    in_window(db, c)
    res = engine.create_reservation(db, customer=c, party=2, start=at(future_day(), start), source="whatsapp", actor=SYS)
    db.commit()
    return res


def token_from(caption):
    return re.search(r"/q/([A-Za-z0-9_-]+)", caption).group(1)


def test_reservation_qr_confirmation_and_checkin(db, owner, restaurant, wa):
    res = booked(db)
    drain()
    kind, to, caption = wa.sent[0]
    assert kind == "image" and to == "+919876500001" and res.ref in caption and "Guests: 2" in caption
    token = token_from(caption)
    assert db.scalar(select(QrToken)).token_hash != token
    staff = owner
    r = staff.post("/api/checkin/lookup", json={"code": f"https://resto.example/q/{token}"}).json()
    assert r["result"] == "valid" and r["ref"] == res.ref and r["status"] == "confirmed"
    r = staff.post("/api/checkin/confirm", json={"code": token}).json()
    assert r["result"] == "checked_in" and r["status"] == "arrived"
    r = staff.post("/api/checkin/confirm", json={"code": token}).json()
    assert r["result"] == "already_checked_in" and r["scan_count"] == 3
    assert staff.post("/api/checkin/lookup", json={"code": "x" * 43}).json()["result"] == "invalid"
    page = TestClient(app).get(f"/q/{token}").text
    assert res.ref in page and "Asha" not in page and "98765" not in page
    assert TestClient(app).get(f"/q/{token}.png").content.startswith(b"\x89PNG")


def test_reschedule_revokes_old_qr_and_expiry(db, owner, restaurant, wa):
    res = booked(db)
    drain()
    old = token_from(wa.sent[0][2])
    engine.reschedule(db, res, start=at(future_day(), "20:00"), party=2, actor=SYS)
    db.commit()
    drain()
    new = token_from(wa.sent[-1][2])
    assert "Booking updated" in wa.sent[-1][2]
    assert owner.post("/api/checkin/lookup", json={"code": old}).json()["result"] == "revoked"
    assert owner.post("/api/checkin/lookup", json={"code": new}).json()["result"] == "valid"
    db.execute(QrToken.__table__.update().values(expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()
    assert owner.post("/api/checkin/lookup", json={"code": new}).json()["result"] == "expired"


def test_order_qr_requires_ready_and_verified_payment(db, owner, menu, wa, restaurant):
    restaurant.min_payment_type = "none"
    c = get_or_create(db, "9876500001", "Ravi")
    in_window(db, c)
    o = orders.create_draft(db, customer=c, channel="whatsapp", actor=SYS)
    orders.add_item(db, o, item_id=menu["tikka"].id, quantity=1, actor=SYS)
    orders.confirm(db, o, actor=SYS)
    db.commit()
    owner.post(f"/api/orders/{o.ref}/status", json={"status": "accepted", "eta_minutes": 5})
    drain()
    caption = next(s[2] for s in wa.sent if s[0] == "image")
    assert "Estimated ready" in caption and "Pay ₹294 at the counter" in caption
    token = token_from(caption)
    assert owner.post("/api/checkin/confirm", json={"code": token}).json()["result"] == "not_ready"
    owner.post(f"/api/orders/{o.ref}/status", json={"status": "ready"})
    r = owner.post("/api/checkin/confirm", json={"code": token}).json()
    assert r["result"] == "handed_over" and r["balance_due_paise"] == 29400
    assert owner.post("/api/checkin/confirm", json={"code": token}).json()["result"] == "already_collected"


def test_notification_policy_window_consent_templates(db, restaurant, wa):
    c = get_or_create(db, "9876500002", "Out Of Window")
    res = engine.create_reservation(db, customer=c, party=2, start=at(future_day(), "19:00"), source="voice", actor=SYS)
    db.commit()
    drain()
    n = db.scalar(select(Notification).where(Notification.kind == "booking_confirmation"))
    assert n.status == "skipped" and "consent" in n.error and wa.sent == []
    assert db.scalar(select(Alert).where(Alert.kind == "notification_skipped"))
    c.whatsapp_opt_in = True
    restaurant.whatsapp_templates = {"booking_confirmation": {"name": "booking_confirmed_v1", "language": "en"}}
    db.commit()
    engine.reschedule(db, res, start=at(future_day(), "20:00"), party=2, actor=SYS)
    db.commit()
    drain()
    kind, to, name, params = wa.sent[0]
    assert kind == "template" and name == "booking_confirmed_v1" and params[2] == res.ref and params[0] == "Out Of Window"


def test_not_on_whatsapp_and_retries_dont_double_send(db, restaurant, wa):
    res = booked(db)
    wa.fail_with = WhatsAppError("503", retryable=True)
    drain()
    assert wa.sent == []
    n = db.scalar(select(Notification))
    assert n.status == "pending"
    for _ in range(2):
        db.execute(Job.__table__.update().where(Job.status == "queued", Job.kind == "notify.reservation").values(run_at=Job.created_at))
        db.commit()
        drain()
    assert len(wa.sent) == 1
    other = get_or_create(db, "9876500003", "No WA")
    in_window(db, other)
    wa.fail_with = WhatsAppError("400 131026: undeliverable", code=131026)
    engine.create_reservation(db, customer=other, party=2, start=at(future_day(), "13:00"), source="voice", actor=SYS)
    db.commit()
    drain()
    db.refresh(other)
    assert other.whatsapp_unavailable and db.scalar(select(Alert).where(Alert.kind == "notification_failed"))


def test_reminder_respects_cancellation_and_reschedule(db, restaurant, wa):
    res = booked(db)
    reminder = db.scalar(select(Job).where(Job.kind == "reservation.reminder"))
    engine.reschedule(db, res, start=at(future_day(), "20:00"), party=2, actor=SYS)
    db.commit()
    db.refresh(reminder)
    assert reminder.status == "cancelled"
    new = db.scalar(select(Job).where(Job.kind == "reservation.reminder", Job.status == "queued"))
    db.execute(Job.__table__.update().where(Job.id == new.id).values(run_at=utcnow()))
    db.commit()
    drain()
    assert any("Reminder" in s[2] for s in wa.sent)


def test_handoff_queue_staff_reply_and_callbacks(db, owner, restaurant, wa):
    c = get_or_create(db, "9876500004", "Unhappy")
    in_window(db, c)
    convo = Conversation(channel="whatsapp", customer_id=c.id, external_id=c.phone)
    db.add(convo)
    db.flush()
    handoff(db, convo, "customer complaint about cold food")
    db.commit()
    q = owner.get("/api/handoff").json()
    assert q["conversations"][0]["id"] == convo.id and q["conversations"][0]["can_reply"]
    assert db.scalar(select(Alert).where(Alert.kind == "complaint"))
    assert db.scalar(select(Job).where(Job.kind == "notify.staff"))
    assert owner.post(f"/api/conversations/{convo.id}/reply", json={"body": "So sorry! Manager calling you now."}).status_code == 200
    assert wa.sent[-1] == ("text", "+919876500004", "So sorry! Manager calling you now.")
    c.last_inbound_whatsapp_at = utcnow() - timedelta(hours=25)
    db.commit()
    assert owner.post(f"/api/conversations/{convo.id}/reply", json={"body": "hello?"}).status_code == 400
    cb = owner.post("/api/callbacks", json={"phone": "9876500004", "reason": "wants manager"}).json()
    assert owner.post(f"/api/callbacks/{cb['id']}/done", json={"note": "called back"}).json()["status"] == "done"
    owner.post(f"/api/conversations/{convo.id}/release")
    db.expire_all()
    assert db.get(Conversation, convo.id).mode == "ai"


def test_dead_job_raises_staff_alert(db):
    from app.core.jobs import enqueue
    enqueue(db, "does.not.exist", {}, max_attempts=1)
    db.commit()
    drain()
    assert db.scalar(select(Job)).status == "dead"
    assert db.scalar(select(Alert).where(Alert.kind == "job_failed")).severity == "error"
