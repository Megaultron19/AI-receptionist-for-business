import hashlib
import hmac
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from .config import config
from .db import now
from .models import Conversation, Failure

GRAPH = "https://graph.facebook.com/v23.0"


class WhatsAppError(Exception):
    pass


def enabled() -> bool:
    return bool(config().whatsapp_token and config().whatsapp_phone_id)


def _post(path: str, **kwargs) -> dict:
    if not enabled():
        raise WhatsAppError("WhatsApp is not set up")
    r = httpx.post(f"{GRAPH}/{config().whatsapp_phone_id}/{path}", headers={"Authorization": f"Bearer {config().whatsapp_token}"},
                   timeout=15, **kwargs)
    if r.status_code >= 400:
        raise WhatsAppError(f"{r.status_code} {r.text[:300]}")
    return r.json()


def send_text(to: str, text: str) -> None:
    _post("messages", json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": text[:4096]}})


def upload_image(png: bytes) -> str:
    return _post("media", files={"file": ("qr.png", png, "image/png")}, data={"messaging_product": "whatsapp", "type": "image/png"})["id"]


def send_image(to: str, media_id: str, caption: str) -> None:
    _post("messages", json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "image",
                            "image": {"id": media_id, "caption": caption[:1024]}})


def send_template(to: str, name: str, params: list[str], image_id: str | None = None) -> None:
    components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
    if image_id:
        components.insert(0, {"type": "header", "parameters": [{"type": "image", "image": {"id": image_id}}]})
    _post("messages", json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
                            "template": {"name": name,
                                         "language": {"code": config().whatsapp_template_language}, "components": components}})


def valid_signature(body: bytes, header: str) -> bool:
    secret = config().whatsapp_app_secret
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(secret) and hmac.compare_digest(expected, header or "")


def can_message_freely(db: Session, phone: str) -> bool:
    convo = db.get(Conversation, phone)
    return bool(convo and convo.last_inbound_at and now() - convo.last_inbound_at < timedelta(hours=24))


def log_failure(db: Session, kind: str, detail: str) -> None:
    db.add(Failure(kind=kind, detail=detail[:2000]))
    db.commit()
