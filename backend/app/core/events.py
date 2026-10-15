"""Audit log, staff alerts, usage metering and integration health. All write into the caller's session
so they commit (or roll back) together with the business change they describe."""
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..db import SessionLocal, utcnow
from .logging import request_id
from .models import Alert, AuditLog, IntegrationStatus, UsageEvent

log = logging.getLogger(__name__)


def audit(db: Session, action: str, entity: str, entity_id: Any = None, *, actor: tuple[str, Any] = ("system", None),
          **data: Any) -> None:
    db.add(AuditLog(actor_type=actor[0], actor_id=None if actor[1] is None else str(actor[1]), action=action,
                    entity=entity, entity_id=None if entity_id is None else str(entity_id), data=data,
                    request_id=request_id.get()))


PAGE_STAFF = {"handoff", "callback", "new_order", "ai_unavailable", "complaint"}


def alert(db: Session, kind: str, message: str, *, severity: str = "info", ref: tuple[str, Any] | None = None) -> Alert:
    """Dashboard alert; important ones are also pushed to the staff WhatsApp numbers."""
    from .jobs import enqueue  # local import: jobs imports this module
    a = Alert(kind=kind, message=message, severity=severity,
              ref_type=ref[0] if ref else None, ref_id=str(ref[1]) if ref else None)
    db.add(a)
    db.flush()
    log.log(logging.WARNING if severity != "info" else logging.INFO, "alert %s: %s", kind, message)
    if severity == "error" or kind in PAGE_STAFF:
        enqueue(db, "notify.staff", {"alert_id": a.id, "message": message[:900]}, dedupe_key=f"staff-alert:{a.id}", max_attempts=3)
    return a


def usage(db: Session, metric: str, quantity: int = 1, cost_paise: int = 0, **meta: Any) -> None:
    db.add(UsageEvent(kind=metric, quantity=quantity, cost_paise=cost_paise, meta=meta))


def integration_result(name: str, ok: bool, error: str | None = None) -> None:
    """Recorded in its own transaction: a provider failure must stay visible even if the caller rolls back."""
    with SessionLocal() as db:
        row = db.get(IntegrationStatus, name) or IntegrationStatus(name=name, consecutive_failures=0)
        if ok:
            row.last_success_at, row.consecutive_failures = utcnow(), 0
        else:
            row.last_failure_at, row.last_error = utcnow(), (error or "")[:2000]
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
        db.merge(row)
        db.commit()
