from sqlalchemy.orm import Session

from ..core.events import alert
from ..core.jobs import handler
from .billing import rupees
from .models import Order


@handler("orders.kitchen_alert")
def kitchen_alert(db: Session, payload: dict) -> None:
    o = db.get(Order, payload["order_id"])
    if o and o.status == "submitted":
        when = "ASAP" if not o.scheduled_for else o.scheduled_for.isoformat(timespec="minutes")
        alert(db, "new_order", f"New {o.order_type.replace('_', '-')} order {o.ref}: {len(o.items)} item(s), {rupees(o.total_paise)}, {when}. "
              "Accept it in Orders.", ref=("order", o.ref))
