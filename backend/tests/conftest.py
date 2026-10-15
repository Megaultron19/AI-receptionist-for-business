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
    """Build the test database with the real migrations, exactly as an installation would."""
    from alembic import command
    from alembic.config import Config
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")
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


@pytest.fixture()
def menu(db, restaurant):
    from app.menu.models import Addon, AddonGroup, ItemVariant, MenuCategory, MenuItem
    restaurant.opening_hours = {d: [["00:00", "23:59"], ["23:59", "00:00"]] for d in restaurant.opening_hours}
    starters, mains, drinks = MenuCategory(name="Starters"), MenuCategory(name="Mains"), MenuCategory(name="Drinks")
    db.add_all([starters, mains, drinks])
    db.flush()
    items = {
        "tikka": MenuItem(category_id=starters.id, name="Paneer Tikka", name_hi="पनीर टिक्का", price_paise=28000, prep_minutes=5, dietary=["veg"]),
        "pbm": MenuItem(category_id=mains.id, name="Paneer Butter Masala", aliases=["PBM"], prep_minutes=12, dietary=["veg"],
                        variants=[ItemVariant(name="Half", price_paise=22000), ItemVariant(name="Full", price_paise=38000, sort=1)]),
        "naan": MenuItem(category_id=mains.id, name="Butter Naan", price_paise=5000, prep_minutes=4),
        "chai": MenuItem(category_id=drinks.id, name="Masala Chai", aliases=["chai", "tea"], price_paise=6000, prep_minutes=3,
                         addon_groups=[AddonGroup(name="Sugar", min_select=1, max_select=1, addons=[
                             Addon(name="Regular sugar"), Addon(name="Less sugar", sort=1), Addon(name="No sugar", sort=2)]),
                             AddonGroup(name="Extras", min_select=0, max_select=2, sort=1, addons=[
                                 Addon(name="Extra ginger", price_paise=1000), Addon(name="Elaichi", price_paise=1000, sort=1)])]),
        "lassi": MenuItem(category_id=drinks.id, name="Sweet Lassi", price_paise=9000, prep_minutes=3, available=False),
    }
    db.add_all(items.values())
    db.commit()
    return items


class FakeRazorpay:
    """In-memory stand-in for the Razorpay API used by app.payments.razorpay."""

    def __init__(self):
        self.links, self.refunds, self.calls, self.fail_next = {}, {}, [], 0

    def _maybe_fail(self):
        from app.payments.razorpay import RazorpayError
        if self.fail_next:
            self.fail_next -= 1
            raise RazorpayError("503: upstream unavailable", 503, True)

    def create_payment_link(self, **kw):
        self.last_create = kw
        self._maybe_fail()
        self.calls.append(("create", kw["reference_id"]))
        lid = f"plink_{len(self.links) + 1}"
        self.links[lid] = {"id": lid, "short_url": f"https://rzp.io/i/{lid}", "status": "created", "amount": kw["amount_paise"],
                           "amount_paid": 0, "reference_id": kw["reference_id"], "payments": [], "notes": kw["notes"]}
        return dict(self.links[lid])

    def fetch_payment_link(self, lid):
        self._maybe_fail()
        return dict(self.links[lid])

    def find_payment_link(self, ref):
        return next((dict(l) for l in self.links.values() if l["reference_id"] == ref), None)

    def cancel_payment_link(self, lid):
        if self.links[lid]["status"] != "created":
            from app.payments.razorpay import RazorpayError
            raise RazorpayError("400: link not cancellable", 400)
        self.links[lid]["status"] = "cancelled"
        return dict(self.links[lid])

    def create_refund(self, payment_id, amount, receipt, notes):
        rid = f"rfnd_{len(self.refunds) + 1}"
        self.refunds[rid] = {"id": rid, "payment_id": payment_id, "amount": amount, "receipt": receipt, "status": "pending"}
        return dict(self.refunds[rid])

    def list_refunds(self, payment_id):
        return [dict(r) for r in self.refunds.values() if r["payment_id"] == payment_id]

    def pay(self, lid, amount=None):
        l = self.links[lid]
        l["status"], l["amount_paid"] = "paid", amount if amount is not None else l["amount"]
        l["payments"] = [{"payment_id": f"pay_{lid}", "status": "captured", "amount": l["amount_paid"]}]


@pytest.fixture()
def rzp(monkeypatch):
    from app.payments import razorpay
    fake = FakeRazorpay()
    for name in ("create_payment_link", "fetch_payment_link", "find_payment_link", "cancel_payment_link", "create_refund", "list_refunds"):
        monkeypatch.setattr(razorpay, name, getattr(fake, name))
    return fake


def razorpay_webhook(client, event: str, payload: dict, event_id: str):
    import hashlib, hmac, json
    body = json.dumps({"event": event, "payload": payload}).encode()
    sig = hmac.new(b"rzp_whsec", body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id,
                                                                     "Content-Type": "application/json"})


class FakeWhatsApp:
    def __init__(self):
        self.sent, self.fail_with = [], None

    def _check(self):
        if self.fail_with:
            err, self.fail_with = self.fail_with, None
            raise err

    def send_text(self, to, body):
        self._check()
        self.sent.append(("text", to, body))
        return f"wamid.{len(self.sent)}"

    def upload_png(self, png):
        assert png.startswith(b"\x89PNG")
        return "media-1"

    def send_image(self, to, media_id, caption):
        self._check()
        self.sent.append(("image", to, caption))
        return f"wamid.{len(self.sent)}"

    def send_template(self, to, name, language, params):
        self._check()
        self.sent.append(("template", to, name, params))
        return f"wamid.{len(self.sent)}"

    def bodies(self):
        return [s[2] if s[0] != "template" else s[2] for s in self.sent]


@pytest.fixture()
def wa(monkeypatch):
    from app.whatsapp import client
    fake = FakeWhatsApp()
    for name in ("send_text", "upload_png", "send_image", "send_template"):
        monkeypatch.setattr(client, name, getattr(fake, name))
    return fake


def in_window(db, customer):
    from app.db import utcnow
    customer.last_inbound_whatsapp_at = utcnow()
    db.commit()


class ScriptedLLM:
    """Deterministic stand-in for an LLM provider. Each script step is either a list of (tool, args)
    calls or a final text (callable steps receive the last tool results and return either)."""
    name = "scripted"

    def __init__(self, *steps):
        self.steps, self.tool_results, self.calls, self.fail = list(steps), [], 0, False

    def add_user(self, transcript, text):
        return [*transcript, {"role": "user", "content": text}]

    def add_tool_results(self, transcript, results):
        self.tool_results.append(results)
        return [*transcript, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": c, "content": r, "is_error": e}
                                                          for c, r, e in results]}]

    def complete(self, *, system_stable, system_dynamic, transcript, tools, timeout, max_retries):
        from app.ai.llm import LLMError, ToolCall, Turn
        self.calls += 1
        self.last_system = system_stable + system_dynamic
        self.last_tools = [t.name for t in tools]
        if self.fail:
            raise LLMError("timeout")
        step = self.steps.pop(0)
        if callable(step):
            step = step(self.tool_results[-1] if self.tool_results else [])
        if isinstance(step, str):
            return [*transcript, {"role": "assistant", "content": [{"type": "text", "text": step}]}], Turn(step, [], "end", 100, 20, "scripted")
        calls = [ToolCall(f"t{self.calls}_{i}", n, a) for i, (n, a) in enumerate(step)]
        return ([*transcript, {"role": "assistant", "content": [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]}],
                Turn("", calls, "tool_use", 100, 20, "scripted"))


@pytest.fixture()
def llm(monkeypatch):
    from app.ai import agent
    holder = {"provider": ScriptedLLM()}
    monkeypatch.setattr(agent, "get_provider", lambda: holder["provider"])

    def script(*steps):
        holder["provider"] = ScriptedLLM(*steps)
        return holder["provider"]
    return script


def wa_inbound(client, text, msg_id, phone="919876500001", name="Asha", mtype="text"):
    import hashlib, hmac, json, time as _t
    msg = {"from": phone, "id": msg_id, "timestamp": str(int(_t.time())), "type": mtype}
    if mtype == "text":
        msg["text"] = {"body": text}
    body = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "1111"},
                                                         "contacts": [{"wa_id": phone, "profile": {"name": name}}],
                                                         "messages": [msg]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"meta_secret", body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


def plivo_post(client, path, params):
    from app.voice.providers import plivo_signature
    url = "https://resto.example" + path
    sig = plivo_signature("plivo_tok", url, params, "nonce1")
    return client.post(path, data=params, headers={"X-Plivo-Signature-V3": sig, "X-Plivo-Signature-V3-Nonce": "nonce1"})


def twilio_post(client, path, params):
    import base64, hashlib, hmac
    url = "https://resto.example" + path
    payload = url + "".join(k + params[k] for k in sorted(params))
    sig = base64.b64encode(hmac.new(b"twilio_tok", payload.encode(), hashlib.sha1).digest()).decode()
    return client.post(path, data=params, headers={"X-Twilio-Signature": sig})
