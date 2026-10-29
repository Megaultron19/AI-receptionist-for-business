import threading

from . import razorpay, receptionist, whatsapp
from .confirmations import send_reminders
from .db import Session, backup_database
from .orders import check_pending_payments
from .waitlist import offer_free_tables

EVERY_SECONDS = 60


def run_once() -> None:
    jobs = [backup_database, receptionist.keep_tunnel_up]
    if razorpay.enabled():
        jobs.append(check_pending_payments)
    if whatsapp.enabled():
        jobs += [send_reminders, offer_free_tables]
    for job in jobs:
        try:
            job()
        except Exception as e:
            with Session() as db:
                whatsapp.log_failure(db, "background_job", f"{job.__name__}: {e}")


def start(stop: threading.Event) -> None:
    def loop():
        while not stop.wait(EVERY_SECONDS):
            run_once()
    threading.Thread(target=loop, daemon=True).start()
