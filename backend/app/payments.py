import json
import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select

from . import razorpay, whatsapp
from .db import Session
from .models import Order
from .orders import check_payment, check_pending_payments

router = APIRouter(prefix="/webhooks/razorpay")
CHECK_EVERY_SECONDS = 60


@router.post("")
async def receive(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not razorpay.valid_webhook(body, request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(403, "Bad signature")
    link_id = json.loads(body).get("payload", {}).get("payment_link", {}).get("entity", {}).get("id")
    with Session() as db:
        order_id = db.scalar(select(Order.id).where(Order.payment_link_id == link_id)) if link_id else None
    if order_id:
        background.add_task(check_payment, order_id)
    return {"ok": True}


def start_checker(stop: threading.Event) -> threading.Thread:
    def loop():
        while not stop.wait(CHECK_EVERY_SECONDS):
            try:
                check_pending_payments()
            except Exception as e:
                with Session() as db:
                    whatsapp.log_failure(db, "razorpay", f"Payment checker: {e}")
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
