from sqlalchemy import select

from app.core.jobs import drain
from app.core.models import Alert
from app.customers.service import get_or_create
from app.orders import service as orders
from app.orders.models import Order
from app.payments.models import Payment
from app.reservations import engine
from app.restaurant.service import get_restaurant

from .conftest import at, future_day, razorpay_webhook

SYS = ("system", None)


def paid_order_flow(db, menu):
    c = get_or_create(db, "9876500001", "Asha")
    o = orders.create_draft(db, customer=c, channel="whatsapp", actor=SYS)
    orders.add_item(db, o, item_id=menu["tikka"].id, quantity=2, actor=SYS)
    orders.confirm(db, o, actor=SYS)
    db.commit()
    return o


def test_payment_link_created_from_server_amount_and_idempotent(db, menu, rzp):
    o = paid_order_flow(db, menu)
    assert o.status == "awaiting_payment" and o.amount_due_paise == o.total_paise == 58800
    rzp.fail_next = 3
    drain()
    p = db.scalar(select(Payment).where(Payment.order_id == o.id))
    assert p.status == "creating"
    from app.core.models import Job
    for _ in range(3):
        db.execute(Job.__table__.update().where(Job.status == "queued").values(run_at=Job.created_at))
        db.commit()
        drain()
    db.refresh(p)
    assert db.get(Job, 1).attempts == 4
    assert p.status == "created" and p.amount_paise == 58800 and p.short_url.startswith("https://rzp.io/")
    assert [c[0] for c in rzp.calls] == ["create"]


def test_webhook_signature_duplicates_and_independent_verification(db, owner, menu, rzp):
    o = paid_order_flow(db, menu)
    drain()
    p = db.scalar(select(Payment).where(Payment.order_id == o.id))
    link = {"payment_link": {"entity": {"id": p.provider_link_id, "status": "paid"}}}
    r = owner.post("/webhooks/razorpay", content=b'{"event":"payment_link.paid"}', headers={"X-Razorpay-Signature": "bad"})
    assert r.status_code == 400
    assert razorpay_webhook(owner, "payment_link.paid", link, "evt_1").json()["duplicate"] is False
    drain()
    db.refresh(p)
    assert p.status == "created"
    rzp.pay(p.provider_link_id)
    razorpay_webhook(owner, "payment_link.paid", link, "evt_2")
    assert razorpay_webhook(owner, "payment_link.paid", link, "evt_2").json()["duplicate"] is True
    drain()
    db.expire_all()
    p, o = db.get(Payment, p.id), db.get(Order, o.id)
    assert p.status == "paid" and p.provider_payment_id.startswith("pay_")
    assert o.status == "submitted" and o.amount_paid_paise == 58800 and o.invoice_number
    razorpay_webhook(owner, "payment.failed", {"payment": {"entity": {"id": p.provider_payment_id, "error_description": "bank declined"}}}, "evt_3")
    drain()
    db.expire_all()
    assert db.get(Payment, p.id).status == "paid" and db.get(Order, o.id).status == "submitted"


def test_failed_attempt_then_success(db, owner, menu, rzp):
    o = paid_order_flow(db, menu)
    drain()
    p = db.scalar(select(Payment).where(Payment.order_id == o.id))
    razorpay_webhook(owner, "payment.authorized", {"payment": {"entity": {"id": "pay_x", "notes": {"payment_ref": p.ref}}}}, "e1")
    drain()
    db.expire_all()
    assert db.get(Order, o.id).status == "payment_pending"
    razorpay_webhook(owner, "payment.failed", {"payment": {"entity": {"id": "pay_x", "notes": {"payment_ref": p.ref}, "error_description": "UPI timeout"}}}, "e2")
    drain()
    db.expire_all()
    assert db.get(Order, o.id).status == "awaiting_payment" and db.get(Payment, p.id).last_failure == "UPI timeout"
    rzp.pay(p.provider_link_id)
    from app.payments.service import reconcile
    db.execute(Payment.__table__.update().values(created_at=Payment.created_at - __import__("datetime").timedelta(minutes=5)))
    db.commit()
    reconcile(db)
    db.commit()
    assert db.get(Order, o.id).status == "submitted"


def test_expired_link_cancels_order(db, owner, menu, rzp):
    o = paid_order_flow(db, menu)
    drain()
    p = db.scalar(select(Payment).where(Payment.order_id == o.id))
    rzp.links[p.provider_link_id]["status"] = "expired"
    razorpay_webhook(owner, "payment_link.expired", {"payment_link": {"entity": {"id": p.provider_link_id}}}, "e1")
    drain()
    db.expire_all()
    assert db.get(Payment, p.id).status == "expired" and db.get(Order, o.id).status == "cancelled"


def test_edit_after_link_then_late_payment_is_refunded(db, owner, menu, rzp):
    o = paid_order_flow(db, menu)
    drain()
    old = db.scalar(select(Payment).where(Payment.order_id == o.id))
    rzp.pay(old.provider_link_id)
    orders.reopen_for_edit(db, o, actor=SYS)
    db.commit()
    drain()
    db.expire_all()
    old = db.get(Payment, old.id)
    assert old.status == "paid" and len(old.refunds) == 1 and old.refunds[0].status == "pending"
    assert db.scalar(select(Alert).where(Alert.kind == "late_payment"))
    rid = old.refunds[0].provider_refund_id
    razorpay_webhook(owner, "refund.processed", {"refund": {"entity": {"id": rid, "status": "processed", "receipt": old.refunds[0].ref}}}, "e9")
    drain()
    db.expire_all()
    assert db.get(Payment, old.id).status == "refunded" and db.get(Order, o.id).status == "draft"


def test_restaurant_rejects_paid_order_refund_flow(db, owner, menu, rzp):
    o = paid_order_flow(db, menu)
    drain()
    p = db.scalar(select(Payment).where(Payment.order_id == o.id))
    rzp.pay(p.provider_link_id)
    razorpay_webhook(owner, "payment_link.paid", {"payment_link": {"entity": {"id": p.provider_link_id}}}, "e1")
    drain()
    r = owner.post(f"/api/orders/{o.ref}/status", json={"status": "cancelled", "reason": "out of paneer"})
    assert r.status_code == 200
    drain()
    db.expire_all()
    p = db.get(Payment, p.id)
    assert p.refunds and p.refunds[0].amount_paise == 58800
    r = owner.post(f"/api/payments/{p.ref}/refund", json={"amount_paise": 100, "reason": "double refund"})
    assert r.status_code == 400


def test_deposit_confirms_reservation_only_after_verified_payment(db, owner, restaurant, rzp):
    r = get_restaurant(db)
    r.deposit_min_party, r.deposit_per_guest_paise = 4, 20000
    db.commit()
    c = get_or_create(db, "9876500001", "Big Group")
    res = engine.create_reservation(db, customer=c, party=4, start=at(future_day(), "19:00"), source="whatsapp", actor=SYS)
    db.commit()
    assert res.status == "held" and res.deposit_paise == 80000
    drain()
    p = db.scalar(select(Payment).where(Payment.reservation_id == res.id))
    assert p.amount_paise == 80000 and p.status == "created"
    rzp.pay(p.provider_link_id)
    razorpay_webhook(owner, "payment_link.paid", {"payment_link": {"entity": {"id": p.provider_link_id}}}, "e1")
    drain()
    db.expire_all()
    assert db.get(type(res), res.id).status == "confirmed"
