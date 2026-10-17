import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ.update(DASHBOARD_DIR="/nonexistent", WHATSAPP_TOKEN="t", WHATSAPP_PHONE_ID="1", WHATSAPP_APP_SECRET="secret",
                  WHATSAPP_VERIFY_TOKEN="verify", ANTHROPIC_API_KEY="k")

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


class FakeWhatsApp:
    def __init__(self):
        self.sent, self.fail = [], False

    def send_text(self, to, text):
        if self.fail:
            raise RuntimeError("network down")
        self.sent.append(("text", to, text))

    def upload_image(self, png):
        assert png.startswith(b"\x89PNG")
        return "media-1"

    def send_image(self, to, media_id, caption):
        self.sent.append(("image", to, caption))

    def send_template(self, to, media_id, params):
        self.sent.append(("template", to, params))


@pytest.fixture
def wa(monkeypatch):
    from app import whatsapp
    fake = FakeWhatsApp()
    for name in ("send_text", "upload_image", "send_image", "send_template"):
        monkeypatch.setattr(whatsapp, name, getattr(fake, name))
    return fake


class Block_:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self, **_):
        return dict(self.__dict__)


class FakeClaude:
    def __init__(self, steps):
        self.steps, self.requests = list(steps), []
        self.beta = self
        self.messages = self

    def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        step = self.steps.pop(0)
        if isinstance(step, str):
            return Block_(stop_reason="end_turn", content=[Block_(type="text", text=step)])
        calls = [Block_(type="tool_use", id=f"t{len(self.requests)}{i}", name=n, input=a) for i, (n, a) in enumerate(step)]
        return Block_(stop_reason="tool_use", content=calls)


@pytest.fixture
def claude(monkeypatch):
    from app import agent
    holder = {}

    def script(*steps):
        holder["c"] = FakeClaude(steps)
        monkeypatch.setattr(agent, "client", lambda: holder["c"])
        return holder["c"]
    return script


def whatsapp_post(c, text, msg_id, phone="919876500001", name="Asha"):
    import hashlib, hmac, json
    body = json.dumps({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": phone, "profile": {"name": name}}],
                                                         "messages": [{"from": phone, "id": msg_id, "type": "text", "text": {"body": text}}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    return c.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
