import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["DASHBOARD_DIR"] = "/nonexistent"

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import create_user
from app.db import Base, Session, engine, now
from app.main import app
from app.models import DiningTable
from app.reservations import restaurant


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        r = restaurant(db)
        r.hours = {d: [["12:00", "23:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        db.add_all([DiningTable(name="T1", seats=2), DiningTable(name="T2", seats=2),
                    DiningTable(name="T3", seats=4), DiningTable(name="T4", seats=6)])
        create_user(db, "owner", "owner-pass-1", "owner")
        create_user(db, "door", "door-pass-1", "staff")
        db.commit()
    yield


@pytest.fixture
def db():
    with Session() as s:
        yield s


def day(offset: int = 3) -> date:
    return now().date() + timedelta(days=offset)


def at(hhmm: str, offset: int = 3) -> datetime:
    return datetime.combine(day(offset), time.fromisoformat(hhmm))


def client(username: str = "owner", password: str = "owner-pass-1") -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    c.headers["X-Requested-With"] = "dashboard"
    return c
