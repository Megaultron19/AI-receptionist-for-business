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


def test_change_my_password():
    door = client("door", "door-pass-1")
    other = client("door", "door-pass-1")
    assert door.post("/api/auth/password", json={"current": "wrong", "new": "door-pass-2"}).json()["detail"] == "Current password is wrong"
    assert door.post("/api/auth/password", json={"current": "door-pass-1", "new": "short"}).status_code == 400
    assert door.post("/api/auth/password", json={"current": "door-pass-1", "new": "door-pass-2"}).status_code == 200
    assert door.get("/api/auth/me").status_code == 200
    assert other.get("/api/auth/me").status_code == 401
    client("door", "door-pass-2")


def test_forgotten_owner_password(capsys):
    from app.cli import reset_password
    message = reset_password("OWNER")
    temporary = message.split(": ")[1].split("\n")[0]
    owner = client("owner", temporary)
    assert owner.get("/api/auth/me").json()["must_change_password"]
    owner.post("/api/auth/password", json={"current": temporary, "new": "brand-new-pass"})
    assert not owner.get("/api/auth/me").json()["must_change_password"]
    assert "No login called ghost. Logins: door, owner" == reset_password("ghost")


def test_owner_set_password_must_be_changed():
    owner = client()
    door_id = [u for u in owner.get("/api/users").json() if u["username"] == "door"][0]["id"]
    owner.post(f"/api/users/{door_id}/password", json={"password": "temp-pass-1"})
    assert client("door", "temp-pass-1").get("/api/auth/me").json()["must_change_password"]
