"""Minimal Razorpay REST client (Payment Links + Refunds). Server-side only: secrets never reach a browser.
Docs: https://razorpay.com/docs/api/payments/payment-links/ and /refunds/."""
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from ..config import get_settings
from ..core.events import integration_result

log = logging.getLogger(__name__)
BASE = "https://api.razorpay.com/v1"
RETRYABLE = {429, 500, 502, 503, 504}


class RazorpayError(Exception):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status, self.retryable = status, retryable


def configured() -> bool:
    s = get_settings()
    return bool(s.razorpay_key_id and s.razorpay_key_secret)


def request(method: str, path: str, json: dict | None = None, params: dict | None = None, attempts: int = 3) -> dict[str, Any]:
    s = get_settings()
    if not configured():
        raise RazorpayError("Razorpay is not configured (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET).")
    last: RazorpayError | None = None
    for attempt in range(attempts):
        try:
            r = httpx.request(method, BASE + path, json=json, params=params, auth=(s.razorpay_key_id, s.razorpay_key_secret),
                              timeout=httpx.Timeout(15, connect=5))
        except httpx.HTTPError as e:
            last = RazorpayError(f"network error: {e}", retryable=True)
        else:
            if r.status_code < 400:
                integration_result("razorpay", True)
                return r.json()
            desc = r.json().get("error", {}).get("description", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            last = RazorpayError(f"{r.status_code}: {desc}"[:500], r.status_code, r.status_code in RETRYABLE)
            if not last.retryable:
                break
        time.sleep(min(0.5 * 2 ** attempt, 4))
    integration_result("razorpay", False, str(last))
    raise last


def create_payment_link(*, amount_paise: int, reference_id: str, description: str, customer_name: str, contact: str,
                        expire_by: int, notes: dict[str, str]) -> dict[str, Any]:
    return request("POST", "/payment_links", json={
        "amount": amount_paise, "currency": "INR", "accept_partial": False, "reference_id": reference_id,
        "description": description[:2048], "customer": {"name": customer_name[:100] or "Guest", "contact": contact},
        # We deliver the link ourselves over WhatsApp; Razorpay SMS/email off to avoid duplicate messages.
        "notify": {"sms": False, "email": False}, "reminder_enable": False, "expire_by": expire_by, "notes": notes,
    })


def fetch_payment_link(link_id: str) -> dict[str, Any]:
    return request("GET", f"/payment_links/{link_id}")


def find_payment_link(reference_id: str) -> dict[str, Any] | None:
    links = request("GET", "/payment_links", params={"reference_id": reference_id}).get("payment_links", [])
    return links[0] if links else None


def cancel_payment_link(link_id: str) -> dict[str, Any]:
    return request("POST", f"/payment_links/{link_id}/cancel")


def create_refund(payment_id: str, amount_paise: int, receipt: str, notes: dict[str, str]) -> dict[str, Any]:
    return request("POST", f"/payments/{payment_id}/refund",
                   json={"amount": amount_paise, "speed": "normal", "receipt": receipt, "notes": notes})


def list_refunds(payment_id: str) -> list[dict[str, Any]]:
    return request("GET", f"/payments/{payment_id}/refunds").get("items", [])


def verify_webhook(raw_body: bytes, signature: str) -> bool:
    secret = get_settings().razorpay_webhook_secret
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
