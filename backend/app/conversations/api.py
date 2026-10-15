from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..core.errors import DomainError, NotFound
from ..core.events import audit, usage
from ..core.models import Alert
from ..customers.service import get_or_create, in_service_window
from ..db import get_db, utcnow
from ..deps import actor, require
from ..whatsapp import client as wa
from . import service
from .models import Call, CallbackRequest, Conversation, Message

router = APIRouter(prefix="/api", tags=["conversations"])


def convo_out(c: Conversation, last: Message | None = None) -> dict:
    return {"id": c.id, "channel": c.channel, "mode": c.mode, "status": c.status, "handoff_reason": c.handoff_reason,
            "handoff_at": c.handoff_at, "language": c.language, "last_message_at": c.last_message_at, "unread": c.unread,
            "customer": {"id": c.customer.id, "name": c.customer.name, "phone": c.customer.phone,
                         "whatsapp_opt_in": c.customer.whatsapp_opt_in},
            "can_reply": c.channel == "whatsapp" and in_service_window(c.customer),
            "last_message": last.body[:200] if last else ""}


def msg_out(m: Message) -> dict:
    return {"id": m.id, "direction": m.direction, "sender": m.sender, "body": m.body, "media": m.media, "status": m.status,
            "error": m.error, "template": m.template, "created_at": m.created_at}


@router.get("/conversations")
def inbox(channel: str = "whatsapp", mode: str | None = None, db: Session = Depends(get_db),
          _: StaffUser = Depends(require("inbox.view"))):
    stmt = select(Conversation).where(Conversation.channel == channel).order_by(Conversation.last_message_at.desc()).limit(200)
    if mode:
        stmt = stmt.where(Conversation.mode == mode)
    out = []
    for c in db.scalars(stmt):
        last = db.scalar(select(Message).where(Message.conversation_id == c.id).order_by(Message.id.desc()).limit(1))
        out.append(convo_out(c, last))
    return out


@router.get("/conversations/{cid}")
def conversation(cid: int, db: Session = Depends(get_db), _: StaffUser = Depends(require("inbox.view"))):
    c = db.get(Conversation, cid)
    if not c:
        raise NotFound("Conversation")
    c.unread = False
    db.commit()
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.id)).all()
    return convo_out(c) | {"messages": [msg_out(m) for m in msgs], "state": c.state}


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/conversations/{cid}/reply")
def reply(cid: int, body: ReplyIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("inbox.reply"))):
    c = db.scalar(select(Conversation).where(Conversation.id == cid).with_for_update(of=Conversation))
    if not c or c.channel != "whatsapp":
        raise NotFound("WhatsApp conversation")
    if not in_service_window(c.customer):
        raise DomainError("More than 24 hours since the customer's last message: WhatsApp only allows approved templates now. "
                          "Call the customer instead.")
    try:
        mid = wa.send_text(c.customer.phone, body.body)
    except wa.WhatsAppError as e:
        raise DomainError(f"WhatsApp didn't accept the message: {e}", "provider_error", 502)
    if c.mode == "ai":
        service.handoff(db, c, "staff replied", actor=actor(user))  # staff took over; AI stays quiet until released
    c.assigned_to, c.last_message_at = user.id, utcnow()
    db.add(Message(conversation_id=c.id, customer_id=c.customer_id, direction="out", sender="staff", body=body.body,
                   wa_message_id=mid, status="sent", staff_id=user.id))
    usage(db, "whatsapp_out", 1, kind="staff_reply", method="session")
    audit(db, "conversation.staff_reply", "conversation", c.id, actor=actor(user))
    db.commit()
    return {"ok": True}


class HandoffIn(BaseModel):
    reason: str = Field("taken over by staff", max_length=200)


@router.post("/conversations/{cid}/handoff")
def take_over(cid: int, body: HandoffIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("handoff.manage"))):
    c = db.get(Conversation, cid)
    if not c:
        raise NotFound("Conversation")
    service.handoff(db, c, body.reason, actor=actor(user))
    c.assigned_to = user.id
    db.commit()
    return convo_out(c)


@router.post("/conversations/{cid}/release")
def release(cid: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("handoff.manage"))):
    c = db.get(Conversation, cid)
    if not c:
        raise NotFound("Conversation")
    service.release(db, c, actor=actor(user))
    db.commit()
    return convo_out(c)


@router.get("/handoff")
def handoff_queue(db: Session = Depends(get_db), _: StaffUser = Depends(require("handoff.manage"))):
    convos = db.scalars(select(Conversation).where(Conversation.mode == "human", Conversation.status == "open")
                        .order_by(Conversation.handoff_at)).all()
    cbs = db.scalars(select(CallbackRequest).where(CallbackRequest.status == "open").order_by(CallbackRequest.created_at)).all()
    return {"conversations": [convo_out(c) for c in convos],
            "callbacks": [cb_out(cb) for cb in cbs]}


def cb_out(cb: CallbackRequest) -> dict:
    return {"id": cb.id, "phone": cb.phone, "name": cb.customer.name, "reason": cb.reason, "source": cb.source,
            "status": cb.status, "created_at": cb.created_at, "handled_at": cb.handled_at, "note": cb.note}


class CallbackIn(BaseModel):
    phone: str
    name: str = Field("", max_length=120)
    reason: str = Field(min_length=2, max_length=300)


class CallbackDoneIn(BaseModel):
    note: str = Field("", max_length=300)
    status: str = Field("done", pattern="^(done|cancelled)$")


@router.post("/callbacks")
def create_callback(body: CallbackIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("callbacks.manage"))):
    cb = service.request_callback(db, get_or_create(db, body.phone, body.name), body.reason, source="dashboard", actor=actor(user))
    db.commit()
    return cb_out(cb)


@router.post("/callbacks/{cb_id}/done")
def callback_done(cb_id: int, body: CallbackDoneIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("callbacks.manage"))):
    cb = db.get(CallbackRequest, cb_id)
    if not cb or cb.status != "open":
        raise NotFound("Open callback")
    cb.status, cb.note, cb.handled_by, cb.handled_at = body.status, body.note, user.id, utcnow()
    audit(db, f"callback.{body.status}", "callback", cb.id, actor=actor(user))
    db.commit()
    return cb_out(cb)


@router.get("/calls")
def calls(days: int = 7, db: Session = Depends(get_db), _: StaffUser = Depends(require("calls.view"))):
    rows = db.scalars(select(Call).where(Call.started_at > utcnow() - timedelta(days=min(days, 90)))
                      .order_by(Call.started_at.desc()).limit(500))
    return [{"id": c.id, "provider": c.provider, "from_number": c.from_number, "started_at": c.started_at,
             "ended_at": c.ended_at, "duration_seconds": c.duration_seconds, "language": c.language, "turns": c.turns,
             "outcome": c.outcome, "error": c.error, "conversation_id": c.conversation_id} for c in rows]


@router.get("/alerts")
def alerts(open_only: bool = True, db: Session = Depends(get_db), _: StaffUser = Depends(require("alerts.view"))):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(200)
    if open_only:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))
    unread = db.scalar(select(func.count()).select_from(Alert).where(Alert.acknowledged_at.is_(None)))
    return {"unacknowledged": unread, "alerts": [
        {"id": a.id, "kind": a.kind, "severity": a.severity, "message": a.message, "ref_type": a.ref_type, "ref_id": a.ref_id,
         "created_at": a.created_at, "acknowledged_at": a.acknowledged_at} for a in db.scalars(stmt)]}


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("alerts.view"))):
    a = db.get(Alert, alert_id)
    if not a:
        raise NotFound("Alert")
    if not a.acknowledged_at:
        a.acknowledged_at, a.acknowledged_by = utcnow(), user.id
    db.commit()
    return {"ok": True}
