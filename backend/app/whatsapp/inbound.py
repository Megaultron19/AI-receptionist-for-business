"""Incoming WhatsApp messages and delivery statuses (processed in a job so the webhook answers fast)."""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..ai import agent
from ..config import get_settings
from ..conversations import service as convo_service
from ..conversations.models import Conversation, Message, Notification
from ..core.events import usage
from ..core.jobs import enqueue
from ..core.models import WebhookEvent
from ..customers.service import get_or_create
from ..db import utcnow
from ..restaurant.service import get_restaurant
from . import client as wa

log = logging.getLogger(__name__)
NEW_THREAD_AFTER = timedelta(hours=24)
STOP_WORDS = {"stop", "unsubscribe", "band karo"}


def verify_signature(raw: bytes, header: str) -> bool:
    secret = get_settings().meta_app_secret
    if not secret or not header.startswith("sha256="):
        return False
    return hmac.compare_digest("sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), header)


def store(db: Session, payload: dict) -> int:
    """Split a webhook into per-message events, deduplicated by WhatsApp message id (Meta retries)."""
    queued = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("metadata", {}).get("phone_number_id") not in (None, get_settings().meta_phone_number_id):
                continue  # not our number
            for st in value.get("statuses", []):
                _apply_status(db, st)
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                row = db.execute(insert(WebhookEvent).values(
                    provider="whatsapp", event_id=m["id"], event_type=f"message.{m.get('type', '?')}"[:64],
                    payload={"message": m, "profile_name": contacts.get(m.get("from"), "")}, status="received", received_at=utcnow())
                    .on_conflict_do_nothing(constraint="uq_webhook_provider_event").returning(WebhookEvent.id)).scalar()
                if row:
                    enqueue(db, "whatsapp.inbound", {"webhook_id": row}, dedupe_key=f"wa-in:{row}", max_attempts=4)
                    queued += 1
    return queued


def _apply_status(db: Session, st: dict) -> None:
    status = st.get("status")  # sent | delivered | read | failed
    if status not in ("sent", "delivered", "read", "failed"):
        return
    err = (st.get("errors") or [{}])[0]
    error = f"{err.get('code', '')} {err.get('title', '')}".strip()[:300]
    rank = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
    for model in (Message, Notification):
        row = db.scalar(select(model).where(model.wa_message_id == st.get("id")).with_for_update())
        if row and rank.get(status, 0) > rank.get(row.status, 0):  # statuses can arrive out of order
            row.status = status
            if status == "failed":
                row.error = error


def _text(m: dict) -> str | None:
    t = m.get("type")
    if t == "text":
        return m["text"].get("body", "")
    if t == "button":
        return m["button"].get("text", "")
    if t == "interactive":
        i = m["interactive"]
        return (i.get("button_reply") or i.get("list_reply") or {}).get("title", "")
    return None


def process(db: Session, webhook_id: int) -> None:
    ev = db.get(WebhookEvent, webhook_id, with_for_update=True)
    if not ev or ev.status == "processed":
        return
    m = ev.payload["message"]
    customer = get_or_create(db, m["from"], ev.payload.get("profile_name", ""))
    convo = _conversation(db, customer)
    if (pending := convo.state.get("pending_reply")) and pending.get("webhook_id") == webhook_id:
        _reply(db, convo, customer, pending["body"], webhook_id)  # retry after a failed send: resend, don't re-ask the AI
        ev.status, ev.processed_at = "processed", utcnow()
        return
    text = _text(m)
    if not db.scalar(select(Message.id).where(Message.wa_message_id == m["id"])):
        sent_at = datetime.fromtimestamp(int(m["timestamp"]), timezone.utc) if m.get("timestamp") else utcnow()
        customer.last_inbound_whatsapp_at = max(filter(None, [customer.last_inbound_whatsapp_at, sent_at]))
        customer.whatsapp_unavailable = False
        db.add(Message(conversation_id=convo.id, customer_id=customer.id, direction="in", sender="customer",
                       body=text if text is not None else f"[{m.get('type')}]", media="" if text is not None else m.get("type", ""),
                       wa_message_id=m["id"], status="received"))
        convo.last_message_at, convo.unread = utcnow(), True
        usage(db, "whatsapp_in", 1)
        db.commit()  # keep the inbound message even if the AI turn fails

    if convo.mode == "human":
        pass  # staff are handling this thread; it shows as unread in the inbox
    elif text is not None and text.strip().lower() in STOP_WORDS:
        customer.whatsapp_opt_in = False
        _reply(db, convo, customer, "You won't receive further booking or order messages from us on WhatsApp. "
               "Message us any time if you need anything.", webhook_id)
    elif text is None:
        _reply(db, convo, customer, "Sorry, I can only read text messages right now. Please type your request.", webhook_id)
    elif not get_restaurant(db).ai_enabled:
        convo_service.handoff(db, convo, "AI receptionist is switched off")
    else:
        reply = agent.respond(db, convo, customer, text[:2000], channel="whatsapp")
        if reply.ok:
            _reply(db, convo, customer, reply.text, webhook_id)
        else:
            convo_service.handoff(db, convo, "AI unavailable")
            _reply(db, convo, customer, "Sorry, I'm having trouble right now. A member of our staff will reply here shortly.", webhook_id)
    ev.status, ev.processed_at = "processed", utcnow()


def _conversation(db: Session, customer) -> Conversation:
    convo = db.scalar(select(Conversation).where(Conversation.channel == "whatsapp", Conversation.customer_id == customer.id,
                                                 Conversation.status == "open").order_by(Conversation.id.desc()).with_for_update(of=Conversation))
    if convo and convo.mode == "ai" and convo.last_message_at < utcnow() - NEW_THREAD_AFTER and not convo.state.get("pending_reply"):
        convo.status = "closed"  # start a fresh AI thread instead of growing (or rewriting) an old transcript
        convo = None
    if not convo:
        convo = Conversation(channel="whatsapp", customer_id=customer.id, external_id=customer.phone,
                             language=get_restaurant(db).primary_language)
        db.add(convo)
        db.flush()
    return convo


def _reply(db: Session, convo: Conversation, customer, body: str, webhook_id: int) -> None:
    """Send inside the 24h window the customer just opened. The reply (and the AI turn behind it) is saved
    before sending, so if the send fails the job retry resends the same text instead of re-running the AI."""
    convo.state = {**convo.state, "pending_reply": {"webhook_id": webhook_id, "body": body}}
    db.commit()
    mid = wa.send_text(customer.phone, body)
    convo.state = {k: v for k, v in convo.state.items() if k != "pending_reply"}
    db.add(Message(conversation_id=convo.id, customer_id=customer.id, direction="out", sender="ai", body=body,
                   wa_message_id=mid, status="sent"))
    convo.last_message_at = utcnow()
    usage(db, "whatsapp_out", 1, get_settings().cost_whatsapp_service_msg_paise, kind="reply", method="session")
