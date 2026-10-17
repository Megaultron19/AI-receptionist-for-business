import json

from fastapi.testclient import TestClient

from app.db import Session, now
from app.main import app
from app.models import Conversation, MenuItem, Order

from .conftest import at, client, whatsapp_post


def add_menu():
    with Session() as db:
        dishes = [MenuItem(name="Paneer Tikka", price=250, prep_minutes=4), MenuItem(name="Dal Makhani", price=200, prep_minutes=3),
                  MenuItem(name="Biryani", price=350, prep_minutes=25), MenuItem(name="Kulfi", price=90, available=False)]
        db.add_all(dishes)
        db.commit()
        return [d.id for d in dishes]


def test_dashboard_order_bill_edit_and_payment():
    tikka, dal, biryani, kulfi = add_menu()
    c = client()
    booking = c.post("/api/reservations", json={"name": "A", "phone": "9876500010", "guests": 2, "starts_at": at("20:00").isoformat()}).json()
    o = c.post("/api/orders", json={"name": "A", "booking": booking["ref"], "items": [{"menu_item_id": tikka, "qty": 2}]}).json()
    assert o["status"] == "confirmed" and o["total"] == 500 and o["booking"] == booking["ref"] and o["table"] == "T1"
    assert "within 5 minutes of your arrival" in o["ready_note"]
    assert c.post("/api/orders", json={"name": "B", "items": [{"menu_item_id": kulfi, "qty": 1}]}).json()["detail"] == "Kulfi is out of stock today"
    o = c.put(f"/api/orders/{o['ref']}/items", json=[{"menu_item_id": tikka, "qty": 1, "notes": "less spicy"},
                                                    {"menu_item_id": dal, "qty": 1}]).json()
    assert o["total"] == 450 and o["items"][0]["notes"] == "less spicy"
    with Session() as db:
        db.get(MenuItem, tikka).price = 999
        db.commit()
    assert c.get("/api/orders").json()[0]["total"] == 450
    assert c.post(f"/api/orders/{o['ref']}/paid").json()["payment_status"] == "paid"
    assert c.put(f"/api/orders/{o['ref']}/items", json=[{"menu_item_id": dal, "qty": 3}]).status_code == 409
    for status in ("preparing", "ready", "served"):
        assert c.post(f"/api/orders/{o['ref']}/status?status={status}").json()["status"] == status
    assert c.post(f"/api/orders/{o['ref']}/status?status=cancelled").status_code == 409
    assert c.get("/api/orders").json() == []


def test_ready_promise_only_when_possible():
    tikka, dal, biryani, kulfi = add_menu()
    c = client()
    walk_in = c.post("/api/orders", json={"name": "C", "items": [{"menu_item_id": biryani, "qty": 1}]}).json()
    assert walk_in["ready_note"] == "Your food will be ready in about 25 minutes."
    quick = c.post("/api/orders", json={"name": "C", "items": [{"menu_item_id": tikka, "qty": 1}]}).json()
    assert quick["ready_note"] == "Your food will be ready in 5 minutes."


def test_whatsapp_pre_order(wa, claude):
    tikka, dal, biryani, kulfi = add_menu()
    bot = claude([("order_food", {"booking_ref": None, "items": [{"dish_id": kulfi, "qty": 1, "notes": None}]})],
                 [("order_food", {"booking_ref": None, "items": [{"dish_id": tikka, "qty": 2, "notes": None}]})],
                 "That is Rs 500, shall I confirm?")
    c = TestClient(app)
    whatsapp_post(c, "2 paneer tikka and a kulfi", "o1")
    assert "out of stock" in json.loads(bot.requests[1]["messages"][-1]["content"][0]["content"])["error"]
    assert "Total: Rs 500" in json.loads(bot.requests[2]["messages"][-1]["content"][0]["content"])["bill"]
    claude([("confirm_order", {})], "Confirmed!")
    whatsapp_post(c, "yes", "o2")
    assert "Your order is confirmed" in wa.sent[-1][2] and "2 x Paneer Tikka: Rs 500" in wa.sent[-1][2]
    claude([("order_food", {"booking_ref": None, "items": [{"dish_id": tikka, "qty": 1, "notes": None},
                                                           {"dish_id": dal, "qty": 1, "notes": "no butter"}]})], "Updated.")
    whatsapp_post(c, "make it one tikka and add dal without butter", "o3")
    assert "Total: Rs 450" in wa.sent[-1][2] and "(no butter)" in wa.sent[-1][2]
    with Session() as db:
        assert db.query(Order).count() == 1


def test_bad_input_does_not_leave_empty_order_or_crash(wa, claude):
    add_menu()
    bot = claude([("order_food", {"booking_ref": "NOPE12", "items": []}), ], [("cancel_booking", {"ref": "ZZZZZZ"})], "Which booking?")
    whatsapp_post(TestClient(app), "cancel my booking", "o4")
    assert "Booking not found" in bot.requests[1]["messages"][-1]["content"][0]["content"]
    assert "Booking not found" in bot.requests[2]["messages"][-1]["content"][0]["content"]
    assert wa.sent[-1][2] == "Which booking?"
    with Session() as db:
        assert db.query(Order).count() == 0
        assert not db.get(Conversation, "+919876500001").needs_staff
