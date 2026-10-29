from .conftest import client


def test_owner_manages_staff_logins():
    owner = client()
    added = owner.post("/api/users", json={"username": "Ravi", "password": "ravi-pass-1", "role": "staff"}).json()
    assert added == {"id": added["id"], "username": "ravi", "role": "staff", "active": True}
    assert owner.post("/api/users", json={"username": "ravi", "password": "another-1"}).json()["detail"] == "That username is taken"
    assert owner.post("/api/users", json={"username": "x", "password": "short"}).status_code == 400
    ravi = client("ravi", "ravi-pass-1")
    assert ravi.get("/api/users").status_code == 403
    assert owner.post(f"/api/users/{added['id']}/password", json={"password": "new-pass-22"}).status_code == 200
    assert ravi.get("/api/auth/me").status_code == 401
    ravi = client("ravi", "new-pass-22")
    owner.post(f"/api/users/{added['id']}/active?active=false")
    assert ravi.get("/api/auth/me").status_code == 401
    me = [u for u in owner.get("/api/users").json() if u["username"] == "owner"][0]
    assert owner.post(f"/api/users/{me['id']}/active?active=false").status_code == 400
