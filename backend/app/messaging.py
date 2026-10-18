import json
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError

from . import agent, whatsapp
from .config import config
from .confirmations import send_confirmation
from .inbox import add_notice
from .orders import send_order_confirmation
from .db import Session, now
from .models import Conversation, SeenMessage
from .reservations import BookingError, normalize_phone

router = APIRouter(prefix="/webhooks/whatsapp")
FRESH_START_AFTER = timedelta(hours=12)


@router.get("")
def verify(request: Request):
    q = request.query_params
    if config().whatsapp_verify_token and q.get("hub.verify_token") == config().whatsapp_verify_token and q.get("hub.mode") == "subscribe":
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@router.post("")
async def receive(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not whatsapp.valid_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(403, "Bad signature")
    for entry in json.loads(body).get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c["wa_id"]: c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for message in value.get("messages", []):
                background.add_task(handle_message, message, names.get(message.get("from"), ""))
    return {"ok": True}


def first_time(message_id: str) -> bool:
    with Session() as db:
        db.add(SeenMessage(id=message_id))
        try:
            db.commit()
            return True
        except IntegrityError:
            return False


def handle_message(message: dict, profile_name: str) -> None:
    if not first_time(message["id"]):
        return
    try:
        phone = normalize_phone(message["from"])
    except BookingError:
        return
    text = message.get("text", {}).get("body", "").strip() if message.get("type") == "text" else ""
    booked, confirmed = [], []
    with Session() as db:
        convo = db.get(Conversation, phone) or Conversation(phone=phone, name=profile_name, history=[])
        if convo.last_inbound_at and now() - convo.last_inbound_at > FRESH_START_AFTER:
            convo.history = []
        convo.last_inbound_at, convo.updated_at = now(), now()
        db.merge(convo)
        db.commit()
        convo = db.get(Conversation, phone)
        if convo.needs_staff:
            if text:
                convo.history = list(convo.history) + [{"role": "user", "content": text}]
                db.commit()
            return
        if not text:
            answer = "Sorry, I can only read text messages. Please type your message."
        else:
            try:
                answer, turn = agent.reply(db, convo, text)
                booked, confirmed = turn.booked_ids, turn.order_ids
            except Exception as e:
                convo.needs_staff = True
                whatsapp.log_failure(db, "ai_reply", f"{phone}: {e}")
                add_notice(db, f"Chat with {convo.name or phone} needs staff, the AI could not reply")
                answer = "Sorry, I am having trouble right now. Our staff will reply here soon."
        db.commit()
    try:
        whatsapp.send_text(phone, answer)
    except Exception as e:
        with Session() as db:
            whatsapp.log_failure(db, "whatsapp_reply", f"{phone}: {e}")
    for reservation_id in booked:
        send_confirmation(reservation_id)
    for order_id in dict.fromkeys(confirmed):
        send_order_confirmation(order_id)
