"""WhatsApp Business Platform (Cloud API) client. https://developers.facebook.com/docs/whatsapp/cloud-api"""
import logging
from typing import Any

import httpx

from ..config import get_settings
from ..core.events import integration_result

log = logging.getLogger(__name__)
NOT_ON_WHATSAPP = {131026}  # message undeliverable: number can't receive WhatsApp messages
OUTSIDE_WINDOW = {131047}  # more than 24h since the customer's last message: needs a template
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class WhatsAppError(Exception):
    def __init__(self, message: str, code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def configured() -> bool:
    s = get_settings()
    return bool(s.meta_access_token and s.meta_phone_number_id)


def _post(path: str, *, json: dict | None = None, files: dict | None = None, data: dict | None = None) -> dict[str, Any]:
    s = get_settings()
    if not configured():
        raise WhatsAppError("WhatsApp is not configured (META_ACCESS_TOKEN / META_PHONE_NUMBER_ID).")
    url = f"https://graph.facebook.com/{s.meta_graph_version}/{s.meta_phone_number_id}/{path}"
    try:
        r = httpx.post(url, headers={"Authorization": f"Bearer {s.meta_access_token}"}, json=json, files=files, data=data,
                       timeout=httpx.Timeout(15, connect=5))
    except httpx.HTTPError as e:
        integration_result("whatsapp", False, str(e))
        raise WhatsAppError(f"network error: {e}", retryable=True)
    if r.status_code >= 400:
        err = r.json().get("error", {}) if r.headers.get("content-type", "").startswith("application/json") else {}
        code = err.get("code")
        msg = f"{r.status_code} {code}: {err.get('message') or r.text}"[:400]
        retry = r.status_code in RETRYABLE_STATUS or code in (4, 80007, 130429, 131000)
        integration_result("whatsapp", code in NOT_ON_WHATSAPP | OUTSIDE_WINDOW, msg)  # customer-side errors aren't outages
        raise WhatsAppError(msg, code, retry)
    integration_result("whatsapp", True)
    return r.json()


def _message(to: str, payload: dict) -> str:
    out = _post("messages", json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+")} | payload)
    return out["messages"][0]["id"]


def send_text(to: str, body: str) -> str:
    return _message(to, {"type": "text", "text": {"preview_url": True, "body": body[:4096]}})


def upload_png(png: bytes) -> str:
    out = _post("media", files={"file": ("qr.png", png, "image/png")}, data={"messaging_product": "whatsapp", "type": "image/png"})
    return out["id"]


def send_image(to: str, media_id: str, caption: str) -> str:
    return _message(to, {"type": "image", "image": {"id": media_id, "caption": caption[:1024]}})


def send_template(to: str, name: str, language: str, params: list[str]) -> str:
    components = [{"type": "body", "parameters": [{"type": "text", "text": p[:1000]} for p in params]}] if params else []
    return _message(to, {"type": "template", "template": {"name": name, "language": {"code": language}, "components": components}})


def mark_read(message_id: str) -> None:
    try:
        _post("messages", json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id})
    except WhatsAppError:
        pass  # cosmetic only
