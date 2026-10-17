import hashlib
import hmac

import httpx

from .config import config

API = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    pass


def enabled() -> bool:
    return bool(config().razorpay_key_id and config().razorpay_key_secret)


def _call(method: str, path: str, **kwargs) -> dict:
    if not enabled():
        raise RazorpayError("Razorpay is not set up")
    r = httpx.request(method, f"{API}/{path}", auth=(config().razorpay_key_id, config().razorpay_key_secret), timeout=15, **kwargs)
    if r.status_code >= 400:
        raise RazorpayError(f"{r.status_code} {r.text[:300]}")
    return r.json()


def create_link(*, amount: int, reference: str, description: str, name: str, phone: str) -> dict:
    return _call("POST", "payment_links", json={
        "amount": amount * 100, "currency": "INR", "accept_partial": False, "reference_id": reference, "description": description[:2048],
        "customer": {"name": name, "contact": phone}, "notify": {"sms": False, "email": False}, "reminder_enable": False})


def fetch_link(link_id: str) -> dict:
    return _call("GET", f"payment_links/{link_id}")


def cancel_link(link_id: str) -> None:
    _call("POST", f"payment_links/{link_id}/cancel")


def valid_webhook(body: bytes, header: str) -> bool:
    secret = config().razorpay_webhook_secret
    if not secret:
        return False
    return hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), header)
