from fastapi.testclient import TestClient

from app.main import app

from .conftest import future_day, make_client


def test_login_failures_and_rate_limit(db, owner):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "owner@resto.example", "password": "nope"}).status_code == 401
    for _ in range(4):
        c.post("/api/auth/login", json={"email": "owner@resto.example", "password": "nope"})
    r = c.post("/api/auth/login", json={"email": "owner@resto.example", "password": "correct-horse-battery"})
    assert r.status_code == 429


def test_requires_login_and_csrf(db, owner, restaurant):
    assert TestClient(app).get("/api/reservations").status_code == 401
    body = {"phone": "9876543210", "name": "A", "party_size": 2, "starts_at": f"{future_day()}T19:00"}
    no_csrf = TestClient(app, cookies=owner.cookies)
    assert no_csrf.post("/api/reservations", json=body).status_code == 403
    r = owner.post("/api/reservations", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["customer"]["phone"] == "+919876543210" and r.json()["status"] == "confirmed"


def test_role_permissions_enforced_in_backend(db, restaurant):
    staff = make_client(db, "staff")
    recep = make_client(db, "receptionist")
    body = {"phone": "9876543210", "party_size": 2, "starts_at": f"{future_day()}T19:00"}
    assert staff.post("/api/reservations", json=body).status_code == 403
    ref = recep.post("/api/reservations", json=body).json()["ref"]
    assert staff.post(f"/api/reservations/{ref}/status", json={"status": "cancelled"}).status_code == 403
    assert staff.post(f"/api/reservations/{ref}/status", json={"status": "seated"}).status_code == 200
    assert recep.patch("/api/settings", json={"name": "X"}).status_code == 403
    assert recep.get("/api/staff").status_code == 403


def test_staff_management_and_session_revocation(db, owner):
    r = owner.post("/api/staff", json={"name": "Ravi", "email": "ravi@resto.example", "password": "long-password-1", "role": "staff"})
    assert r.status_code == 200
    ravi = TestClient(app)
    assert ravi.post("/api/auth/login", json={"email": "ravi@resto.example", "password": "long-password-1"}).status_code == 200
    assert ravi.get("/api/auth/me").json()["role"] == "staff"
    owner.patch(f"/api/staff/{r.json()['id']}", json={"active": False})
    assert ravi.get("/api/auth/me").status_code == 401
    assert owner.post("/api/staff", json={"name": "X", "email": "x@y.z", "password": "short", "role": "staff"}).status_code == 400


def test_settings_validation(db, owner):
    assert owner.patch("/api/settings", json={"gstin": "BAD"}).status_code == 422
    assert owner.patch("/api/settings", json={"opening_hours": {"mon": [["25:00", "23:00"]]}}).status_code == 422
    assert owner.patch("/api/settings", json={"timezone": "Mars/Base"}).status_code == 422
    r = owner.patch("/api/settings", json={"gstin": "27abcde1234f1z5", "default_tax_rate_bp": 500,
                                           "charges": [{"name": "Packaging", "kind": "flat", "value": 2000, "applies_to": "pickup"}]})
    assert r.status_code == 200 and r.json()["gstin"] == "27ABCDE1234F1Z5"
    assert owner.put("/api/special-days", json={"day": str(future_day()), "closed": True, "note": "Holi"}).status_code == 200
