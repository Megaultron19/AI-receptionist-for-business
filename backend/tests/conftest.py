import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/resto_test")
os.environ.update(SECRET_KEY="x" * 40, PUBLIC_BASE_URL="https://resto.example", ENVIRONMENT="test",
                  RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="rzp_secret", RAZORPAY_WEBHOOK_SECRET="rzp_whsec",
                  META_ACCESS_TOKEN="meta_token", META_APP_SECRET="meta_secret", META_VERIFY_TOKEN="meta_verify",
                  META_PHONE_NUMBER_ID="1111", PLIVO_AUTH_ID="MA1", PLIVO_AUTH_TOKEN="plivo_tok",
                  TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="twilio_tok", ANTHROPIC_API_KEY="test")

from datetime import date, datetime, time, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401
from app.core import ratelimit  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as conn:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    ratelimit.reset()
    yield


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


def future_day(days: int = 7) -> date:
    return (datetime.now(IST) + timedelta(days=days)).date()


def at(day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), IST)


@pytest.fixture()
def restaurant(db):
    """Open 12:00-23:00 daily; tables T1(2) T2(2) T3(4) T4(6); combo T1+T2 seats 4."""
    from app.restaurant.service import get_restaurant
    from app.tables.models import DiningTable, TableCombination
    r = get_restaurant(db)
    r.name = "Spice Route"
    r.opening_hours = {d: [["12:00", "23:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    r.duration_rules = []
    r.default_duration_minutes, r.buffer_minutes, r.slot_interval_minutes = 90, 15, 15
    r.reminder_offsets_minutes = [120]
    t = [DiningTable(code=c, capacity=cap, sort=i) for i, (c, cap) in enumerate([("T1", 2), ("T2", 2), ("T3", 4), ("T4", 6)])]
    db.add_all(t)
    db.flush()
    db.add(TableCombination(name="T1+T2", capacity=4, tables=[t[0], t[1]]))
    db.commit()
    return r


def make_client(db, role: str = "owner", email: str | None = None) -> TestClient:
    from app.auth.service import create_user
    from app.main import app
    email = email or f"{role}@resto.example"
    create_user(db, role.title(), email, "correct-horse-battery", role)
    db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("rr_csrf")
    return c


@pytest.fixture()
def owner(db):
    return make_client(db, "owner")
