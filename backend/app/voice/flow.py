"""Provider-independent call flow: greeting, language choice, AI turns, silence/recognition failures,
transfer, callback and call logging."""
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import agent
from ..config import get_settings
from ..conversations import service as convo_service
from ..conversations.models import Call, Conversation, Message
from ..core.events import audit, usage
from ..core.errors import DomainError
from ..customers.models import Customer
from ..customers.service import get_or_create
from ..db import utcnow
from ..restaurant.service import get_restaurant
from .providers import CallEvent, Provider, action_url

MAX_SILENCES = 2


def _texts(lang: str) -> dict[str, str]:
    hi = lang == "hi-IN"
    return {
        "silence": "माफ़ कीजिए, मुझे सुनाई नहीं दिया। क्या आप दोहरा सकते हैं?" if hi else "Sorry, I didn't catch that. Could you say it again?",
        "bye_silence": "माफ़ कीजिए, आवाज़ नहीं आ रही। कृपया दोबारा कॉल करें। धन्यवाद।" if hi else
        "Sorry, I can't hear you. Please call again. Goodbye.",
        "trouble": "माफ़ कीजिए, अभी तकनीकी दिक्कत है। मैं आपको स्टाफ़ से जोड़ रही हूँ।" if hi else
        "Sorry, I'm having a technical problem. Let me connect you to our staff.",
        "trouble_callback": "माफ़ कीजिए, अभी तकनीकी दिक्कत है। हमारा स्टाफ़ आपको जल्द वापस कॉल करेगा। धन्यवाद।" if hi else
        "Sorry, I'm having a technical problem. Our staff will call you back shortly. Goodbye.",
        "no_answer": "माफ़ कीजिए, स्टाफ़ अभी उपलब्ध नहीं है। हम आपको जल्द वापस कॉल करेंगे। धन्यवाद।" if hi else
        "Sorry, nobody is free right now. We'll call you back shortly. Goodbye.",
        "anything": "क्या मैं और कुछ मदद कर सकती हूँ?" if hi else "Is there anything else I can help with?",
    }


def greeting(r, lang: str) -> str:
    name = r.name_pronunciation or r.name
    if lang == "hi-IN":
        return r.greeting_hi or f"नमस्ते, {name} में कॉल करने के लिए धन्यवाद। मैं रेस्टोरेंट की AI असिस्टेंट हूँ। मैं आपकी कैसे मदद कर सकती हूँ?"
    g = r.greeting_en or f"Namaste! Thank you for calling {name}. I'm the restaurant's AI assistant. How can I help you today?"
    return g + (" हिंदी के लिए 2 दबाएँ।" if "hi-IN" in (r.languages or []) else "")


def _call(db: Session, provider: Provider, ev: CallEvent) -> Call | None:
    return db.scalar(select(Call).where(Call.provider_call_id == ev.call_id).with_for_update())


def incoming(db: Session, provider: Provider, ev: CallEvent) -> str:
    r = get_restaurant(db)
    call = _call(db, provider, ev)
    if call is None:
        try:
            customer = get_or_create(db, ev.from_number)
        except DomainError:
            customer = Customer(phone=f"anon-{secrets.token_hex(6)}", name="", whatsapp_unavailable=True)
            db.add(customer)
            db.flush()
        convo = Conversation(channel="voice", customer_id=customer.id, external_id=ev.call_id, language=r.primary_language)
        db.add(convo)
        db.flush()
        call = Call(provider=provider.name, provider_call_id=ev.call_id, conversation_id=convo.id, from_number=customer.phone,
                    to_number=ev.to_number[:20], language=r.primary_language)
        db.add(call)
        audit(db, "call.started", "call", ev.call_id, actor=("provider", provider.name))
    lang = call.language
    if not r.ai_enabled or not get_settings().anthropic_api_key:
        return _fallback(db, provider, call, r, lang, reason="AI receptionist is switched off")
    return provider.ask(greeting(r, lang), lang, action_url(provider.name, "turn", n=0))


def turn(db: Session, provider: Provider, ev: CallEvent, silences: int) -> str:
    r = get_restaurant(db)
    call = _call(db, provider, ev)
    if not call:
        return incoming(db, provider, ev)
    convo = db.get(Conversation, call.conversation_id)
    lang = convo.language or call.language
    t = _texts(lang)
    if ev.digits == "2" and "hi-IN" in (r.languages or []):
        convo.language = call.language = "hi-IN"
        return provider.ask(greeting(r, "hi-IN"), "hi-IN", action_url(provider.name, "turn", n=0))
    speech = ev.speech.strip()
    if not speech:
        if silences >= MAX_SILENCES:
            call.outcome = call.outcome if call.outcome != "in_progress" else "abandoned"
            return provider.hangup(t["bye_silence"], lang)
        return provider.ask(t["silence"], lang, action_url(provider.name, "turn", n=silences + 1))

    call.turns += 1
    db.add(Message(conversation_id=convo.id, customer_id=convo.customer_id, channel="voice", direction="in", sender="customer", body=speech))
    reply = agent.respond(db, convo, convo.customer, speech, channel="voice")
    if not reply.ok:
        call.error = "AI unavailable"
        return _fallback(db, provider, call, r, lang, reason="AI unavailable during call")
    db.add(Message(conversation_id=convo.id, customer_id=convo.customer_id, channel="voice", direction="out", sender="ai", body=reply.text))
    convo.last_message_at = utcnow()
    if (outcome := reply.flags.get("outcome")) and outcome != "info":
        call.outcome = outcome
    lang = convo.language or lang
    call.language = lang
    if reply.flags.get("transfer"):
        call.outcome = "transferred"
        return provider.transfer(reply.text, lang, r.transfer_number, action_url(provider.name, "dial-result"))
    if reply.flags.get("end_call"):
        if call.outcome == "in_progress":
            call.outcome = "info"
        return provider.hangup(reply.text, lang)
    return provider.ask(reply.text, lang, action_url(provider.name, "turn", n=0))


def _fallback(db: Session, provider: Provider, call: Call, r, lang: str, reason: str) -> str:
    """No AI: put the caller through to staff, or record a callback."""
    t = _texts(lang)
    convo = db.get(Conversation, call.conversation_id)
    if r.transfer_number:
        call.outcome = "transferred"
        return provider.transfer(t["trouble"], lang, r.transfer_number, action_url(provider.name, "dial-result"))
    convo_service.request_callback(db, convo.customer, reason, source="voice", actor=("system", None))
    call.outcome = "callback"
    return provider.hangup(t["trouble_callback"], lang)


def dial_result(db: Session, provider: Provider, ev: CallEvent) -> str:
    call = _call(db, provider, ev)
    lang = call.language if call else "en-IN"
    if ev.dial_status in ("completed", "answer", "answered"):
        return provider.xml("<Hangup/>")
    if call:
        convo = db.get(Conversation, call.conversation_id)
        convo_service.request_callback(db, convo.customer, f"transfer not answered ({ev.dial_status or 'no answer'})",
                                       source="voice", actor=("system", None))
        call.outcome = "callback"
    return provider.hangup(_texts(lang)["no_answer"], lang)


def status(db: Session, provider: Provider, ev: CallEvent) -> None:
    """Hangup/status callback: record duration and close the call log."""
    call = _call(db, provider, ev)
    if not call or call.ended_at:
        return
    call.ended_at = utcnow()
    call.duration_seconds = ev.duration or int((call.ended_at - call.started_at).total_seconds())
    if call.outcome == "in_progress":
        call.outcome = "info" if call.turns else "abandoned"
    if ev.status in ("failed", "busy", "no-answer"):
        call.outcome, call.error = "failed", ev.status
    usage(db, "voice_seconds", call.duration_seconds,
          -(-call.duration_seconds // 60) * get_settings().cost_voice_per_minute_paise, provider=provider.name)
    usage(db, "voice_call", 1, provider=provider.name, outcome=call.outcome)
    convo = db.get(Conversation, call.conversation_id)
    if convo:
        convo.status = "closed"
    audit(db, "call.ended", "call", call.provider_call_id, actor=("provider", provider.name),
          outcome=call.outcome, duration=call.duration_seconds)
