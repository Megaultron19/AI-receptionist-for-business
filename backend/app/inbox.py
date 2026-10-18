from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import whatsapp
from .auth import current_user
from .db import get_db, now
from .models import Conversation, Failure, Notice

router = APIRouter(prefix="/api/inbox")


def add_notice(db: Session, text: str) -> None:
    db.add(Notice(text=text[:1000]))
    db.commit()


def transcript(history: list) -> list[dict]:
    lines = []
    for m in history:
        if m["role"] == "user" and isinstance(m["content"], str):
            lines.append({"who": "customer", "text": m["content"]})
        elif m["role"] == "assistant":
            text = " ".join(b.get("text", "") for b in m["content"] if b.get("type") == "text").strip()
            if text:
                lines.append({"who": "staff" if m.get("staff") else "receptionist", "text": text})
    return lines


class ChatIn(BaseModel):
    phone: str
    text: str = Field("", max_length=4000)


def chat(db: Session, phone: str) -> Conversation:
    convo = db.get(Conversation, phone)
    if not convo:
        raise HTTPException(404, "Chat not found")
    return convo


@router.get("")
def inbox(db: Session = Depends(get_db), _=Depends(current_user)):
    chats = db.scalars(select(Conversation).where(Conversation.needs_staff).order_by(Conversation.last_inbound_at.desc()))
    return {
        "chats": [{"phone": c.phone, "name": c.name, "last_message_at": c.last_inbound_at, "can_reply": whatsapp.can_message_freely(db, c.phone),
                   "transcript": transcript(c.history)[-30:]} for c in chats],
        "notices": [{"id": n.id, "text": n.text, "seen": n.seen, "at": n.created_at}
                    for n in db.scalars(select(Notice).order_by(Notice.id.desc()).limit(50))],
        "problems": [{"kind": f.kind, "detail": f.detail, "at": f.created_at} for f in db.scalars(select(Failure).order_by(Failure.id.desc()).limit(30))],
    }


@router.get("/count")
def count(db: Session = Depends(get_db), _=Depends(current_user)):
    unseen = db.scalar(select(func.count()).select_from(Notice).where(Notice.seen.is_(False)))
    waiting = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.needs_staff))
    return {"count": unseen + waiting}


@router.post("/seen")
def mark_seen(db: Session = Depends(get_db), _=Depends(current_user)):
    for n in db.scalars(select(Notice).where(Notice.seen.is_(False))):
        n.seen = True
    db.commit()
    return {"ok": True}


@router.post("/reply")
def reply(body: ChatIn, db: Session = Depends(get_db), _=Depends(current_user)):
    convo = chat(db, body.phone)
    if not body.text.strip():
        raise HTTPException(422, "Type a message first")
    db.commit()
    try:
        whatsapp.send_text(convo.phone, body.text.strip())
    except Exception as e:
        whatsapp.log_failure(db, "whatsapp_staff_reply", f"{convo.phone}: {e}")
        raise HTTPException(502, "WhatsApp did not accept the message. It is only possible within 24 hours of the customer's last message.")
    convo.history = list(convo.history) + [{"role": "assistant", "staff": True, "content": [{"type": "text", "text": body.text.strip()}]}]
    convo.updated_at = now()
    db.commit()
    return {"ok": True}


@router.post("/release")
def release(body: ChatIn, db: Session = Depends(get_db), _=Depends(current_user)):
    chat(db, body.phone).needs_staff = False
    db.commit()
    return {"ok": True}
