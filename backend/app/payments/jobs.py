from sqlalchemy.orm import Session

from ..core.jobs import handler, periodic
from . import service


@handler("payments.order_link")
def order_link(db: Session, payload: dict) -> None:
    service.create_order_link(db, payload["order_id"])


@handler("payments.reservation_deposit")
def deposit_link(db: Session, payload: dict) -> None:
    service.create_deposit_link(db, payload["id"])


@handler("payments.process_webhook")
def process_webhook(db: Session, payload: dict) -> None:
    service.process_webhook(db, payload["webhook_id"])


@handler("payments.refund")
def refund(db: Session, payload: dict) -> None:
    service.execute_refund(db, payload["refund_id"])


@handler("payments.refund_order")
def refund_order(db: Session, payload: dict) -> None:
    service.refund_order(db, payload["order_id"], payload.get("reason", "order cancelled"))


@handler("payments.cancel_order_links")
def cancel_links(db: Session, payload: dict) -> None:
    service.cancel_open_links(db, payload["order_id"])


@handler("payments.reconcile")
def reconcile(db: Session, payload: dict) -> None:
    service.reconcile(db)


periodic("payments.reconcile", 300)
