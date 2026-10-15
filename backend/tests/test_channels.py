from fastapi.testclient import TestClient
from sqlalchemy import select

from app.conversations.models import Call, CallbackRequest, Conversation, Message
from app.core.jobs import drain
from app.core.models import Alert, UsageEvent
from app.main import app
from app.whatsapp.client import WhatsAppError

from .conftest import plivo_post, twilio_post, wa_inbound

CALL = {"CallUUID": "c-9", "From": "919876500009", "To": "918045550123"}


def test_voice_rejects_unsigned_requests(db, restaurant):
    c = TestClient(app)
    assert c.post("/voice/plivo/answer", data=CALL, headers={"X-Plivo-Signature-V3": "x", "X-Plivo-Signature-V3-Nonce": "n"}).status_code == 403
    assert c.post("/voice/twilio/answer", data={"CallSid": "CA1"}, headers={"X-Twilio-Signature": "x"}).status_code == 403


def test_voice_silence_hindi_and_twilio(db, restaurant, llm):
    c = TestClient(app)
    plivo_post(c, "/voice/plivo/answer", CALL)
    r = plivo_post(c, "/voice/plivo/turn?n=0", CALL | {"Digits": "2"})
    assert 'language="hi-IN"' in r.text and "नमस्ते" in r.text
    r = plivo_post(c, "/voice/plivo/turn?n=0", CALL)
    assert "माफ़ कीजिए" in r.text and "n=1" in r.text
    r = plivo_post(c, "/voice/plivo/turn?n=2", CALL)
    assert "<Hangup/>" in r.text
    assert db.scalar(select(Call)).outcome == "abandoned"
    tw = {"CallSid": "CA77", "From": "+919876500010", "To": "+918045550123"}
    r = twilio_post(c, "/voice/twilio/answer", tw)
    assert "<Gather" in r.text and 'input="speech dtmf"' in r.text
    llm("We're open from 12 to 11 tonight.")
    r = twilio_post(c, "/voice/twilio/turn?n=0", tw | {"SpeechResult": "what time do you close"})
    assert "open from 12 to 11" in r.text and "<Say" in r.text


def test_ai_outage_on_call_transfers_or_takes_callback(db, restaurant, llm):
    c = TestClient(app)
    bot = llm()
    bot.fail = True
    restaurant.transfer_number = "+919800000000"
    db.commit()
    plivo_post(c, "/voice/plivo/answer", CALL)
    r = plivo_post(c, "/voice/plivo/turn?n=0", CALL | {"Speech": "book a table"})
    assert "<Dial" in r.text and "919800000000" in r.text
    assert db.scalar(select(Alert).where(Alert.kind == "ai_unavailable")).severity == "error"
    r = plivo_post(c, "/voice/plivo/dial-result", CALL | {"DialStatus": "no-answer"})
    assert "call you back" in r.text and db.scalar(select(CallbackRequest)).status == "open"
    restaurant.transfer_number = ""
    db.commit()
    call2 = CALL | {"CallUUID": "c-10"}
    plivo_post(c, "/voice/plivo/answer", call2)
    r = plivo_post(c, "/voice/plivo/turn?n=0", call2 | {"Speech": "hello"})
    assert "call you back" in r.text and "<Hangup/>" in r.text


def test_transfer_tool_and_end_call(db, restaurant, llm):
    restaurant.transfer_number = "+919800000000"
    db.commit()
    c = TestClient(app)
    plivo_post(c, "/voice/plivo/answer", CALL)
    llm([("transfer_to_staff", {"reason": "wants the manager"})], "Connecting you now.")
    r = plivo_post(c, "/voice/plivo/turn?n=0", CALL | {"Speech": "let me talk to the manager"})
    assert "Connecting you now" in r.text and "<Dial" in r.text
    assert db.scalar(select(Call)).outcome == "transferred"


def test_whatsapp_webhook_security_status_stop_and_human_mode(db, owner, restaurant, wa, llm):
    c = TestClient(app)
    assert c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "meta_verify", "hub.challenge": "42"}).text == "42"
    assert c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "42"}).status_code == 403
    assert c.post("/webhooks/whatsapp", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403
    llm("Hello! How can I help?")
    wa_inbound(c, "hi", "w1")
    drain()
    out = db.scalar(select(Message).where(Message.direction == "out"))
    assert out.body == "Hello! How can I help?" and out.status == "sent"
    import hashlib, hmac, json
    for st in ("read", "delivered"):
        body = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "1111"},
                                                             "statuses": [{"id": out.wa_message_id, "status": st}]}}]}]}).encode()
        c.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=" + hmac.new(b"meta_secret", body, hashlib.sha256).hexdigest()})
    db.refresh(out)
    assert out.status == "read"
    wa_inbound(c, "STOP", "w2")
    drain()
    convo = db.scalar(select(Conversation))
    assert not convo.customer.whatsapp_opt_in and "won't receive" in wa.sent[-1][2]
    owner.post(f"/api/conversations/{convo.id}/handoff", json={"reason": "manager handling"})
    bot = llm("should not be called")
    wa_inbound(c, "are you there?", "w3")
    drain()
    assert bot.calls == 0
    wa_inbound(c, "", "w4", mtype="audio")
    drain()


def test_whatsapp_send_failure_retries_without_rerunning_ai(db, restaurant, wa, llm):
    from app.core.models import Job
    c = TestClient(app)
    bot = llm("Here's our menu...")
    wa.fail_with = WhatsAppError("503", retryable=True)
    wa_inbound(c, "menu?", "w9")
    drain()
    assert wa.sent == [] and bot.calls == 1
    db.execute(Job.__table__.update().where(Job.status == "queued").values(run_at=Job.created_at))
    db.commit()
    drain()
    assert wa.sent[-1][2] == "Here's our menu..." and bot.calls == 1


def test_whatsapp_ai_outage_hands_off(db, restaurant, wa, llm):
    c = TestClient(app)
    llm().fail = True
    wa_inbound(c, "need a table", "w11")
    drain()
    assert "staff will reply" in wa.sent[-1][2]
    assert db.scalar(select(Conversation)).mode == "human"
    assert db.scalar(select(UsageEvent).where(UsageEvent.kind == "whatsapp_in"))


def test_withheld_caller_ids_are_isolated(db, restaurant, llm):
    c = TestClient(app)
    a, b = CALL | {"CallUUID": "w-1", "From": "anonymous"}, CALL | {"CallUUID": "w-2", "From": "anonymous"}
    plivo_post(c, "/voice/plivo/answer", a)
    plivo_post(c, "/voice/plivo/answer", b)
    phones = {cl.from_number for cl in db.scalars(select(Call))}
    assert len(phones) == 2 and all(p.startswith("anon-") for p in phones)
    bot = llm("I can help with questions; for bookings please call from your own number.")
    plivo_post(c, "/voice/plivo/turn?n=0", a | {"Speech": "any bookings for me?"})
    assert "caller ID withheld" in bot.last_system
