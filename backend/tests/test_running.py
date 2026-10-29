import os
import stat

from fastapi.testclient import TestClient

from app import receptionist
from app.config import config
from app.db import Session, backup_database, now
from app.models import Reservation
from app.main import app
from app.models import Failure

from .conftest import at, client, whatsapp_post


def fake_cloudflared(tmp_path, monkeypatch):
    script = tmp_path / "cloudflared"
    script.write_text("#!/bin/sh\nsleep 60\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(config(), "cloudflared_path", str(script))
    monkeypatch.setattr(config(), "cloudflare_tunnel_token", "tok")


def test_stopped_receptionist_stays_quiet(wa, claude, monkeypatch):
    from app import phone
    receptionist.state["on"] = False
    bot = claude("hi")
    whatsapp_post(TestClient(app), "hello", "r1")
    assert wa.sent == [] and bot.requests == []
    monkeypatch.setattr(phone, "now", lambda: at("13:00"))
    body = TestClient(app).post("/webhooks/plivo/answer?key=pk", data={"CallUUID": "c", "From": "919876500001"}).text
    assert "closed right now" in body


def test_start_and_stop_with_tunnel(tmp_path, monkeypatch):
    fake_cloudflared(tmp_path, monkeypatch)
    receptionist.state["on"] = False
    c = client()
    assert c.get("/api/receptionist").json()["tunnel"] == "stopped"
    started = c.post("/api/receptionist/start").json()
    assert started["on"] and started["tunnel"] == "running" and started["ready"]["Internet tunnel"]
    receptionist.state["tunnel"].kill()
    receptionist.state["tunnel"].wait()
    assert c.get("/api/receptionist").json()["tunnel"] == "down"
    receptionist.keep_tunnel_up()
    assert c.get("/api/receptionist").json()["tunnel"] == "running"
    with Session() as db:
        assert db.query(Failure).one().kind == "tunnel"
    stopped = c.post("/api/receptionist/stop").json()
    assert not stopped["on"] and stopped["tunnel"] == "stopped"


def test_missing_cloudflared_is_explained(monkeypatch):
    monkeypatch.setattr(config(), "cloudflare_tunnel_token", "tok")
    monkeypatch.setattr(config(), "cloudflared_path", "/nowhere/cloudflared")
    receptionist.state["on"] = False
    r = client().post("/api/receptionist/start")
    assert r.status_code == 400 and "cloudflared was not found" in r.json()["detail"]
    assert not receptionist.is_on()


def test_login_lockout_and_headers():
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "owner", "password": "wrong-pass"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-1"})
    assert r.status_code == 429
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"


def test_daily_backup(monkeypatch):
    folder = os.path.join(config().data_dir, "backups")
    os.makedirs(folder, exist_ok=True)
    for n in range(20):
        open(os.path.join(folder, f"restaurant-2020-01-{n + 1:02d}.db"), "w").close()
    backup_database()
    backup_database()
    files = sorted(os.listdir(folder))
    assert len(files) == 14 and files[0] == "restaurant-2020-01-08.db"
    import sqlite3
    assert sqlite3.connect(os.path.join(folder, files[-1])).execute("select count(*) from tables").fetchone()[0] == 4


def test_reload_keys_without_restart(monkeypatch):
    c = client()
    assert c.get("/api/receptionist").json()["ready"]["Phone"]
    monkeypatch.setenv("PLIVO_WEBHOOK_KEY", "")
    assert client("door", "door-pass-1").post("/api/receptionist/reload").status_code == 403
    assert not c.post("/api/receptionist/reload").json()["ready"]["Phone"]
    monkeypatch.undo()
    config.cache_clear()


def test_door_staff_seats_walk_in():
    door = client("door", "door-pass-1")
    tables = {t["name"]: t["id"] for t in door.get("/api/tables").json()}
    block = door.post(f"/api/tables/{tables['T3']}/walk-in").json()
    assert block["reason"] == "Walk-in"
    assert "already blocked" in door.post(f"/api/tables/{tables['T3']}/walk-in").json()["detail"]
    door.delete(f"/api/blocks/{block['id']}")
    assert door.post(f"/api/tables/{tables['T3']}/walk-in").status_code == 200


def test_walk_in_refused_when_table_is_booked():
    from datetime import timedelta
    start = now() + timedelta(minutes=30)
    with Session() as db:
        db.add(Reservation(ref="WALK01", name="Meera", phone="+919876500090", guests=2, starts_at=start,
                           ends_at=start + timedelta(minutes=90), table_id=1))
        db.commit()
    r = client("door", "door-pass-1").post("/api/tables/1/walk-in")
    assert r.status_code == 409 and "booking for Meera" in r.json()["detail"]
