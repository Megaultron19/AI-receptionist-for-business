import hmac
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import DomainError
from ..db import get_db
from . import inbound

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


@router.get("")
def verify(request: Request):
    """Meta's subscription handshake."""
    q, token = request.query_params, get_settings().meta_verify_token
    if token and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), token):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise DomainError("Verification failed", "forbidden", 403)


@router.post("")
async def receive(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not inbound.verify_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
        raise DomainError("Bad signature", "bad_signature", 403)
    queued = inbound.store(db, json.loads(raw))
    db.commit()
    return {"ok": True, "queued": queued}
