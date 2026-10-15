import json
import os

from app.cli import main as cli
from app.core.jobs import drain
from app.customers.service import get_or_create
from app.menu.models import MenuItem
from app.reservations import engine
from app.tables.models import DiningTable

from .conftest import at, future_day, make_client

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "sample-restaurant.json")


def test_seed_export_import_roundtrip(db, owner):
    assert cli(["seed-demo", "--file", SAMPLE]) == 0
    assert db.query(DiningTable).count() == 5 and db.query(MenuItem).count() == 7
    exported = owner.get("/api/config/export").json()
    assert exported["settings"]["name"] == "Spice Route (Demo)" and "razorpay" not in json.dumps(exported).lower()
    assert all("secret" not in k for k in exported["settings"])
    r = owner.post("/api/config/import", json={"config": exported, "replace_menu": True})
    assert r.status_code == 200 and r.json()["menu_items"] == 7
    assert db.query(MenuItem).filter(MenuItem.active).count() == 7
    bad = dict(exported, version=99)
    assert owner.post("/api/config/import", json={"config": bad}).status_code == 400


def test_usage_health_reports_audit_and_privacy(db, owner, restaurant, wa):
    c = get_or_create(db, "9876500001", "Asha")
    res = engine.create_reservation(db, customer=c, party=2, start=at(future_day(), "19:00"), source="voice", actor=("system", None))
    db.commit()
    drain()
    u = owner.get("/api/usage?days=7").json()
    assert u["totals"]["reservation_created"]["quantity"] == 1
    h = owner.get("/api/health/integrations").json()
    assert h["integrations"]["razorpay"]["configured"] and not h["worker"]["alive"]
    d = str(future_day())
    rep = owner.get(f"/api/reports/summary?start={d}&end={d}").json()
    assert rep["reservations_by_status"] == {"confirmed": 1} and rep["reservations_by_source"] == {"voice": 1}
    assert any(a["action"] == "reservation.created" for a in owner.get("/api/audit").json())
    assert owner.get("/api/overview").json()["alerts_open"] >= 0
    exp = owner.get(f"/api/customers/{c.id}/export").json()
    assert exp["customer"]["phone"] == "+919876500001" and exp["reservations"][0]["ref"] == res.ref
    assert owner.post(f"/api/customers/{c.id}/anonymize").status_code == 400  # upcoming booking must be cancelled first
    engine.transition(db, res, "cancelled", actor=("system", None))
    db.commit()
    assert owner.post(f"/api/customers/{c.id}/anonymize").status_code == 200
    db.refresh(c)
    assert c.name == "" and not c.phone.startswith("+91") and c.anonymized_at
    manager = make_client(db, "manager")
    assert manager.get(f"/api/customers/{c.id}/export").status_code == 403  # owner only
