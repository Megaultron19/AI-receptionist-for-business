import hmac
import re
from xml.sax.saxutils import escape, quoteattr

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import agent, whatsapp
from .auth import current_user
from .config import config
from .confirmations import send_confirmation
from .db import Session, get_db, now
from .inbox import add_notice, transcript
from .models import Call
from .orders import send_order_confirmation
from .reservations import BookingError, is_open, normalize_phone, restaurant

router = APIRouter()
DEVANAGARI = re.compile(r"[\u0900-\u097f]")
MAX_SILENCES = 2


def xml(*parts: str) -> Response:
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>", media_type="application/xml")


def language(text: str) -> str:
    return "hi-IN" if DEVANAGARI.search(text) else "en-IN"


def speak(text: str) -> str:
    return f"<Speak voice={quoteattr(config().plivo_voice)} language={quoteattr(language(text))}>{escape(text)}</Speak>"


def listen(say: str, lang: str) -> str:
    url = f"{config().public_url}/webhooks/plivo/turn?key={config().plivo_webhook_key}"
    return (f'<GetInput action={quoteattr(url)} method="POST" inputType="speech" language="{lang}" executionTimeout="20" '
            f'speechEndTimeout="2" redirect="true">{speak(say)}</GetInput>'
            f'<Redirect method="POST">{escape(url)}</Redirect>')


def transfer(staff_phone: str) -> str:
    return f"<Dial><Number>{escape(staff_phone.lstrip('+'))}</Number></Dial>"


async def form(request: Request) -> dict:
    if not config().plivo_webhook_key or not hmac.compare_digest(request.query_params.get("key", ""), config().plivo_webhook_key):
        raise HTTPException(403, "Bad key")
    return dict(await request.form())


@router.post("/webhooks/plivo/answer")
async def answer(request: Request):
    data = await form(request)
    with Session() as db:
        r = restaurant(db)
        if not is_open(r, now()):
            return xml(speak(f"Thank you for calling {r.name}. The restaurant is closed right now. Please call later."),
                       speak("अभी रेस्टोरेंट बंद है। कृपया बाद में कॉल करें।"), "<Hangup/>")
        try:
            phone = normalize_phone(data.get("From", ""))
        except BookingError:
            phone = ""
        db.merge(Call(id=data.get("CallUUID", ""), phone=phone, history=[], outcome="in progress", started_at=now(), silences=0,
                      language="en-IN"))
        db.commit()
        greeting = f"Namaste, thank you for calling {r.name}. How can I help you?"
    return xml(listen(greeting, "en-IN"))


@router.post("/webhooks/plivo/turn")
async def turn(request: Request, background: BackgroundTasks):
    data = await form(request)
    speech = (data.get("Speech") or "").strip()
    with Session() as db:
        call = db.get(Call, data.get("CallUUID", ""))
        if not call:
            return xml(speak("Sorry, something went wrong. Please call again."), "<Hangup/>")
        if not speech:
            call.silences += 1
            if call.silences > MAX_SILENCES:
                call.outcome = "no speech"
                db.commit()
                return xml(speak("I could not hear you. Please call again. Goodbye."), "<Hangup/>")
            db.commit()
            again = "माफ़ कीजिए, मैं सुन नहीं पाया। फिर से बताइए?" if call.language == "hi-IN" else "Sorry, I did not catch that. Could you say it again?"
            return xml(listen(again, call.language))
        call.silences = 0
        staff_phone = restaurant(db).staff_phone
        try:
            if not call.phone:
                raise BookingError("caller number hidden")
            said, done = agent.reply(db, call, speech, channel="phone")
        except Exception as e:
            call.needs_staff, said, done = True, "Sorry, I am having trouble. Let me connect you to our staff.", None
            whatsapp.log_failure(db, "call_ai", f"{call.phone or 'hidden number'}: {e}")
        if done:
            if done.order_ids:
                call.outcome = "ordered"
            if done.booked_ids:
                call.outcome = "booked"
            for reservation_id in done.booked_ids:
                background.add_task(send_confirmation, reservation_id)
            for order_id in dict.fromkeys(done.order_ids):
                background.add_task(send_order_confirmation, order_id)
        if call.needs_staff:
            call.outcome = "transferred" if staff_phone else "needs callback"
            db.commit()
            if not staff_phone:
                add_notice(db, f"Call back {call.phone or 'a caller with a hidden number'}, they wanted to talk to staff")
            if staff_phone:
                return xml(speak(said or "Connecting you to our staff."), transfer(staff_phone))
            return xml(speak("Our staff will call you back soon. Thank you."), "<Hangup/>")
        call.language = language(said)
        db.commit()
    return xml(listen(said, call.language))


@router.post("/webhooks/plivo/hangup")
async def hangup(request: Request):
    data = await form(request)
    with Session() as db:
        call = db.get(Call, data.get("CallUUID", ""))
        if call:
            call.ended_at = now()
            if call.outcome == "in progress":
                call.outcome = "answered"
            db.commit()
    return {"ok": True}



@router.get("/api/calls")
def list_calls(db: DbSession = Depends(get_db), _=Depends(current_user)):
    calls = db.scalars(select(Call).order_by(Call.started_at.desc()).limit(100))
    return [{"id": c.id, "phone": c.phone, "started_at": c.started_at, "ended_at": c.ended_at, "outcome": c.outcome,
             "transcript": transcript(c.history)} for c in calls]
