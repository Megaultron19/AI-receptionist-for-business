import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.db import Session, make_engine, migrate, now
from app.main import app
from app.models import Conversation, Failure, Order
from app.orders import check_pending_payments

from .conftest import client, whatsapp_post
from .test_orders import add_menu


def chat_order(claude, dish, qty=2):
    claude([("order_food", {"booking_ref": None, "items": [{"dish_id": dish, "qty": qty, "notes": None}]}), ("confirm_order", {})], "Done.")
    whatsapp_post(TestClient(app), "order", f"p{qty}{dish}")


def webhook(link_id, secret="hook"):
    body = json.dumps({"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": link_id, "status": "paid"}}}}).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return TestClient(app).post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})


def order():
    with Session() as db:
        return db.query(Order).one()


def test_link_sent_with_bill_and_webhook_marks_paid_once(wa, claude, rzp):
    tikka, *_ = add_menu()
    chat_order(claude, tikka)
    assert rzp.links["plink_1"]["amount"] == 50000
    assert "Pay online: https://rzp.io/l/plink_1" in wa.sent[-1][2]
    assert webhook("plink_1").json() == {"ok": True}
    assert order().payment_status == "unpaid"
    assert webhook("plink_1", secret="wrong").status_code == 403
    rzp.pay("plink_1")
    webhook("plink_1")
    webhook("plink_1")
    check_pending_payments()
    o = order()
    assert o.payment_status == "paid" and o.payment_id == "pay_plink_1" and o.paid_at
    assert [m[2] for m in wa.sent].count("Payment of Rs 500 received for order " + o.ref + ". Thank you!") == 1


def test_wrong_amount_is_not_accepted(wa, claude, rzp):
    tikka, *_ = add_menu()
    chat_order(claude, tikka)
    rzp.pay("plink_1", amount=1)
    check_pending_payments()
    assert order().payment_status == "unpaid"


def test_edit_replaces_link_and_paid_link_blocks_edit(wa, claude, rzp):
    tikka, dal, *_ = add_menu()
    chat_order(claude, tikka)
    claude([("order_food", {"booking_ref": None, "items": [{"dish_id": dal, "qty": 1, "notes": None}]})], "Updated.")
    whatsapp_post(TestClient(app), "only dal", "e1")
    assert rzp.cancelled == ["plink_1"]
    assert "Total: Rs 200" in wa.sent[-1][2] and "plink_2" in wa.sent[-1][2]
    rzp.pay("plink_2")
    bot = claude([("order_food", {"booking_ref": None, "items": [{"dish_id": dal, "qty": 3, "notes": None}]})], "Sorry.")
    whatsapp_post(TestClient(app), "make it 3", "e2")
    assert "just been paid online" in bot.requests[1]["messages"][-1]["content"][0]["content"]
    assert order().payment_status == "paid" and order().total == 200


def test_customer_says_paid(wa, claude, rzp):
    tikka, *_ = add_menu()
    chat_order(claude, tikka)
    rzp.pay("plink_1")
    bot = claude([("my_order", {})], "Got it, thanks!")
    whatsapp_post(TestClient(app), "I have paid", "s1")
    assert json.loads(bot.requests[1]["messages"][-1]["content"][0]["content"])["payment"] == "paid"


def test_cash_payment_cancels_link_and_dashboard_check(wa, rzp):
    tikka, *_ = add_menu()
    with Session() as db:
        db.merge(Conversation(phone="+919876500020", history=[], last_inbound_at=now()))
        db.commit()
    c = client()
    o = c.post("/api/orders", json={"name": "A", "phone": "9876500020", "items": [{"menu_item_id": tikka, "qty": 1}]}).json()
    assert c.get("/api/orders").json()[0]["payment_link"] == "https://rzp.io/l/plink_1"
    assert c.post(f"/api/orders/{o['ref']}/check-payment").json()["payment_status"] == "unpaid"
    paid = c.post(f"/api/orders/{o['ref']}/paid").json()
    assert paid["payment_status"] == "paid" and paid["payment_id"] == "cash" and rzp.cancelled == ["plink_1"]


def test_link_failure_still_sends_bill(wa, claude, rzp, monkeypatch):
    from app import razorpay
    tikka, *_ = add_menu()

    def down(**_):
        raise razorpay.RazorpayError("500 down")
    monkeypatch.setattr(razorpay, "create_link", down)
    chat_order(claude, tikka)
    assert "pay at the restaurant" in wa.sent[-1][2]
    with Session() as db:
        assert db.query(Failure).one().kind == "razorpay"


def test_migrate_adds_new_columns(tmp_path):
    old = create_engine(f"sqlite:///{tmp_path}/old.db")
    with old.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE orders (id INTEGER PRIMARY KEY, ref VARCHAR(10), name VARCHAR(120))")
        conn.exec_driver_sql("INSERT INTO orders (id, ref, name) VALUES (1, 'ABC123', 'Old')")
    engine = make_engine(f"sqlite:///{tmp_path}/old.db")
    migrate(engine)
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT name, payment_status, payment_link_id, total FROM orders").one()
    assert tuple(row) == ("Old", "unpaid", "", 0)
