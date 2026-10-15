from sqlalchemy.orm import Session

from ..core.events import alert, audit
from ..customers.models import Customer
from ..db import utcnow
from .models import CallbackRequest, Conversation


def handoff(db: Session, convo: Conversation, reason: str, *, actor: tuple[str, object] = ("ai", None)) -> None:
    """Stop the AI on this conversation and queue it for staff."""
    if convo.mode == "human":
        return
    convo.mode, convo.handoff_reason, convo.handoff_at, convo.unread = "human", reason[:200], utcnow(), True
    kind = "complaint" if "complain" in reason.lower() else "handoff"
    alert(db, kind, f"{convo.channel.title()} conversation with {convo.customer.name or convo.customer.phone} needs staff: {reason}",
          severity="warning", ref=("conversation", convo.id))
    audit(db, "conversation.handoff", "conversation", convo.id, actor=actor, reason=reason[:200])


def release(db: Session, convo: Conversation, *, actor: tuple[str, object]) -> None:
    convo.mode, convo.assigned_to = "ai", None
    audit(db, "conversation.released_to_ai", "conversation", convo.id, actor=actor)


def request_callback(db: Session, customer: Customer, reason: str, *, source: str, actor: tuple[str, object] = ("ai", None)) -> CallbackRequest:
    cb = CallbackRequest(customer_id=customer.id, phone=customer.phone, reason=reason[:300], source=source)
    db.add(cb)
    db.flush()
    alert(db, "callback", f"Callback requested by {customer.name or customer.phone} ({customer.phone}): {reason}",
          severity="warning", ref=("callback", cb.id))
    audit(db, "callback.requested", "callback", cb.id, actor=actor, source=source)
    return cb
