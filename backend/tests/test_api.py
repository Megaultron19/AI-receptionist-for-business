from fastapi.testclient import TestClient

from app.main import app

from .conftest import at, client, day


def test_login_and_request_checks():
    c = TestClient(app)
    assert c.get("/api/menu").status_code == 401
    assert c.post("/api/auth/login", json={"username": "owner", "password": "nope"}).status_code == 401
    c.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-1"})
    assert c.get("/api/menu").status_code == 200
    assert c.post("/api/menu", json={"name": "Tea", "price": 30}).status_code == 403
    c.post("/api/auth/logout", headers={"X-Requested-With": "dashboard"})
    assert c.get("/api/menu").status_code == 401


def test_menu_management_and_roles():
    owner, door = client(), client("door", "door-pass-1")
    item = owner.post("/api/menu", json={"name": "Paneer Tikka", "category": "Starters", "price": 280}).json()
    assert door.post("/api/menu", json={"name": "X", "price": 10}).status_code == 403
    assert door.post(f"/api/menu/{item['id']}/available?available=false").json()["available"] is False
    edited = owner.put(f"/api/menu/{item['id']}", json={**item, "price": 300}).json()
    assert edited["price"] == 300
    assert owner.post("/api/menu", json={"name": "Free", "price": 0}).status_code == 422
    assert owner.delete(f"/api/menu/{item['id']}").status_code == 200
    assert owner.get("/api/menu").json() == []


def test_tables_and_blocks():
    owner = client()
    t = owner.post("/api/tables", json={"name": "Patio", "seats": 4}).json()
    assert owner.post("/api/tables", json={"name": "Patio", "seats": 2}).status_code == 400
    assert owner.post(f"/api/tables/{t['id']}/available?available=false").json()["available"] is False
    b = owner.post("/api/blocks", json={"table_id": None, "starts_at": at("19:00").isoformat(), "ends_at": at("18:00").isoformat()})
    assert b.status_code == 400
    b = owner.post("/api/blocks", json={"starts_at": at("19:00").isoformat(), "ends_at": at("21:00").isoformat(), "reason": "Event"})
    assert b.json()["reason"] == "Event"
    owner.post("/api/reservations", json={"name": "A", "phone": "9876543210", "guests": 2, "starts_at": at("13:00").isoformat()})
    assert owner.delete("/api/tables/1").status_code == 400


def test_booking_api():
    owner = client()
    times = owner.get(f"/api/reservations/availability?day={day()}&guests=2").json()
    assert times[0] == "12:00" and "21:30" in times and "22:00" not in times
    r = owner.post("/api/reservations", json={"name": "Asha", "phone": "98765 43210", "guests": 4, "starts_at": at("19:00").isoformat()})
    body = r.json()
    assert r.status_code == 200 and body["phone"] == "+919876543210" and body["table"] == "T3" and len(body["ref"]) == 6
    for _ in range(2):
        owner.post("/api/reservations", json={"name": "B", "phone": "9876543211", "guests": 6, "starts_at": at("19:00").isoformat()})
    full = owner.post("/api/reservations", json={"name": "C", "phone": "9876543212", "guests": 6, "starts_at": at("19:00").isoformat()})
    assert full.status_code == 409 and full.json()["detail"]["alternatives"]
    moved = owner.put(f"/api/reservations/{body['ref']}", json={"guests": 2, "starts_at": at("20:00").isoformat()}).json()
    assert moved["table"] == "T1"
    assert owner.post(f"/api/reservations/{body['ref']}/status?status=arrived").json()["status"] == "arrived"
    assert owner.get(f"/api/reservations?day={day()}&q=asha").json()[0]["ref"] == body["ref"]


def test_restaurant_settings():
    owner, door = client(), client("door", "door-pass-1")
    s = owner.get("/api/restaurant").json()
    assert owner.put("/api/restaurant", json={**s, "hours": {"mon": [["25:00", "23:00"]]}}).status_code == 422
    saved = owner.put("/api/restaurant", json={**s, "name": "Spice Route"}).json()
    assert saved["name"] == "Spice Route" and saved["hours"] == s["hours"]
    assert door.put("/api/restaurant", json=s).status_code == 403
