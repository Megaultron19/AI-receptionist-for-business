"""End-to-end flows through the real HTTP webhooks, job queue, database and domain services, with only the
external providers (LLM, WhatsApp, Razorpay, telephony signatures) simulated."""
import json
import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.conversations.models import Call, Conversation
from app.core.jobs import drain
from app.main import app
from app.orders.models import Order
from app.payments.models import Payment
from app.reservations.models import Reservation, WaitlistEntry
from app.tables.models import DiningTable

from .conftest import future_day, plivo_post, razorpay_webhook, wa_inbound


def results(llm_provider, i=-1):
    return [json.loads(r[1]) for r in llm_provider.tool_results[i]]


def test_flow1_whatsapp_reservation_to_qr_checkin(db, owner, restaurant, wa, llm):
    day = str(future_day())
    bot = llm([("check_availability", {"date": day, "time": "20:00", "party_size": 2})],
              [("create_reservation", {"date": day, "time": "20:00", "party_size": 2, "name": "Asha", "special_requests": "window seat"})],
              lambda res: f"Done! Your table is booked, reference {json.loads(res[0][1])['ref']}.")
    public = TestClient(app)
    assert wa_inbound(public, "Hi, table for 2 tomorrow at 8pm please, name Asha", "wamid.in1").json()["queued"] == 1
    assert wa_inbound(public, "Hi, table for 2 tomorrow at 8pm please, name Asha", "wamid.in1").json()["queued"] == 0  # Meta retry
    drain()
    assert results(bot, 0)[0]["available"] is True
    created = results(bot, 1)[0]
    assert created["status"] == "confirmed"
    res = db.scalar(select(Reservation))
    assert res.ref == created["ref"] and res.notes == "window seat" and res.source == "whatsapp"
    texts = [s for s in wa.sent if s[0] == "text"]
    assert texts[0][2] == f"Done! Your table is booked, reference {res.ref}."
    qr_msg = next(s for s in wa.sent if s[0] == "image")
    token = re.search(r"/q/([\w-]+)", qr_msg[2]).group(1)
    assert "Spice Route" in qr_msg[2] and res.ref in qr_msg[2]
    assert owner.post("/api/checkin/confirm", json={"code": token}).json()["result"] == "checked_in"
    db.refresh(res)
    assert res.status == "arrived"
    assert "AI assistant" in bot.last_system and "Never invent" in bot.last_system


def test_flow2_voice_preorder_edit_pay_accept_pickup(db, owner, menu, wa, rzp, llm):
    call = {"CallUUID": "call-1", "From": "919876500001", "To": "918045550123"}
    public = TestClient(app)
    r = plivo_post(public, "/voice/plivo/answer", call)
    assert "<GetInput" in r.text and "AI assistant" in r.text and "Polly.Aditi" in r.text

    bot = llm([("start_order", {"order_type": "pickup", "reservation_ref": None}),
               ("add_to_order", {"dish": "paneer", "quantity": 2, "option": None, "addons": [], "instructions": None})],
              lambda res: "Do you mean Paneer Tikka or Paneer Butter Masala?")
    r = plivo_post(public, "/voice/plivo/turn?n=0", call | {"Speech": "I want to order two paneer"})
    assert "Paneer Tikka or Paneer Butter Masala" in r.text
    assert "could be" in json.loads(bot.tool_results[0][1][1])["error"]  # ambiguity reported, not guessed

    bot = llm([("add_to_order", {"dish": "paneer tikka", "quantity": 2, "option": None, "addons": [], "instructions": "extra spicy"})],
              [("add_to_order", {"dish": "chai", "quantity": 1, "option": None, "addons": ["less sugar", "extra ginger"], "instructions": None})],
              lambda res: "Two paneer tikka and one masala chai. Anything else?")
    plivo_post(public, "/voice/plivo/turn?n=0", call | {"Speech": "paneer tikka, extra spicy, and a chai less sugar with ginger"})
    order = results(bot, 1)[0]
    assert order["subtotal"] == "₹630" and order["total"] == "₹661.50"  # 2x280 + 70, plus 5% GST — computed by the backend

    line = next(l for l in order["lines"] if l["dish"] == "Paneer Tikka")["line_id"]
    bot = llm([("change_order_line", {"line_id": line, "quantity": 3, "option": None, "addons": None, "instructions": None}), ("view_order", {})],
              [("record_whatsapp_consent", {"agreed": True}), ("confirm_order", {"pickup_time": None, "customer_gstin": None})],
              lambda res: "Your order is placed. I've sent the payment link on WhatsApp.")
    plivo_post(public, "/voice/plivo/turn?n=0", call | {"Speech": "make it three paneer tikka, then yes confirm and send on WhatsApp"})
    summary = results(bot, 0)[1]
    assert summary["total"] == "₹955.50" and summary["preparation_estimate"]["meets_target"] is True
    confirmed = results(bot, 1)[1]
    assert confirmed["status"] == "awaiting_payment" and "only after the payment is verified" in confirmed["next_step"]

    o = db.scalar(select(Order))
    assert o.total_paise == 95550 and o.amount_due_paise == 95550
    drain()  # payment link job; customer isn't in the WhatsApp window but agreed on the call
    p = db.scalar(select(Payment).where(Payment.order_id == o.id))
    assert p.amount_paise == 95550 and rzp.last_create["sms"] is True  # no approved template configured -> Razorpay SMS fallback
    rzp.pay(p.provider_link_id)
    razorpay_webhook(public, "payment_link.paid", {"payment_link": {"entity": {"id": p.provider_link_id}}}, "evt-pay")
    drain()
    db.expire_all()
    o = db.get(Order, o.id)
    assert o.status == "submitted" and o.amount_paid_paise == 95550   # paid, then waiting for the restaurant
    assert owner.post(f"/api/orders/{o.ref}/status", json={"status": "accepted", "eta_minutes": 5}).json()["status"] == "accepted"
    owner.post(f"/api/orders/{o.ref}/status", json={"status": "preparing"})
    owner.post(f"/api/orders/{o.ref}/status", json={"status": "ready"})
    from app.qr.service import issue
    token = issue(db, order=db.get(Order, o.id))
    db.commit()
    r = owner.post("/api/checkin/confirm", json={"code": token}).json()
    assert r["result"] == "handed_over" and r["payment_verified"]
    plivo_post(public, "/voice/plivo/status", call | {"Duration": "95", "CallStatus": "completed"})
    c = db.scalar(select(Call))
    db.refresh(c)
    assert c.outcome == "order" and c.duration_seconds == 95 and c.turns == 3


def test_flow3_cancellation_releases_table_to_waitlist(db, owner, restaurant, wa, llm):
    for t in (2, 3, 4):
        db.get(DiningTable, t).active = False
    db.commit()
    day = str(future_day())
    public = TestClient(app)
    llm([("create_reservation", {"date": day, "time": "19:00", "party_size": 2, "name": "Asha", "special_requests": None})], "Booked!")
    wa_inbound(public, "book 7pm for 2", "m1")
    drain()
    res = db.scalar(select(Reservation))
    bot = llm([("join_waitlist", {"date": day, "earliest_time": "18:45", "latest_time": "19:30", "party_size": 2})],
              "You're on the waitlist; we'll message you if a table frees up.")
    wa_inbound(public, "Any table around 7?", "m2", phone="919876522222", name="Ravi")
    drain()
    assert results(bot)[0]["waitlisted"] is True

    bot = llm([("find_my_reservations", {})], lambda r: [("cancel_reservation", {"ref": json.loads(r[0][1])["reservations"][0]["ref"]})],
              "Your booking is cancelled.")
    wa_inbound(public, "please cancel my booking", "m3")
    drain()
    db.expire_all()
    assert db.get(Reservation, res.id).status == "cancelled"
    assert any("has been cancelled" in s[2] for s in wa.sent if s[1] == "+919876500001")
    entry = db.scalar(select(WaitlistEntry))
    assert entry.status == "offered"
    offer = next(s for s in wa.sent if s[1] == "+919876522222" and "Reply YES" in s[2])
    held = db.get(Reservation, entry.reservation_id)
    assert held.ref in offer[2] and held.status == "held"
    llm([("respond_to_waitlist_offer", {"ref": held.ref, "accept": True})], "Confirmed! See you at 7.")
    wa_inbound(public, "YES", "m4", phone="919876522222", name="Ravi")
    drain()
    db.expire_all()
    assert db.get(Reservation, held.id).status == "confirmed" and db.get(WaitlistEntry, entry.id).status == "booked"
    assert any(s[0] == "image" and held.ref in s[2] for s in wa.sent)  # QR confirmation for the promoted guest
