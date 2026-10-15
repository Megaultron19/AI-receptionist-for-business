"""Background jobs on Postgres (SELECT … FOR UPDATE SKIP LOCKED).

- enqueue() inside the business transaction; dedupe_key makes enqueueing idempotent.
- Handlers must be idempotent: they re-read current state and do nothing if it is no longer relevant
  (e.g. a reminder for a cancelled booking). A job may run more than once after a crash.
- Failures retry with bounded exponential backoff, then go 'dead' and raise a staff alert.
"""
import logging
import socket
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import SessionLocal, utcnow
from .events import alert
from .models import Job, WorkerHeartbeat

log = logging.getLogger(__name__)

Handler = Callable[[Session, dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}
# name -> (interval seconds, job kind); enqueued by the worker on a fixed cadence.
PERIODIC: dict[str, tuple[int, str]] = {}

BACKOFF_BASE_SECONDS = 15
BACKOFF_CAP_SECONDS = 30 * 60
STALE_LOCK = timedelta(minutes=10)


def handler(kind: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return register


def periodic(kind: str, every_seconds: int):
    PERIODIC[kind] = (every_seconds, kind)


def enqueue(db: Session, kind: str, payload: dict[str, Any] | None = None, *, run_at: datetime | None = None,
            dedupe_key: str | None = None, max_attempts: int = 6) -> None:
    stmt = insert(Job).values(kind=kind, payload=payload or {}, run_at=run_at or utcnow(), dedupe_key=dedupe_key,
                              max_attempts=max_attempts, status="queued", attempts=0, created_at=utcnow())
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"])
    db.execute(stmt)


def cancel_jobs(db: Session, dedupe_prefix: str) -> None:
    db.execute(update(Job).where(Job.dedupe_key.like(f"{dedupe_prefix}%"), Job.status == "queued")
               .values(status="cancelled", finished_at=utcnow()))


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(BACKOFF_BASE_SECONDS * 2 ** (attempts - 1), BACKOFF_CAP_SECONDS))


def run_one() -> bool:
    """Claim and run a single due job. Returns False when nothing was due."""
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.status == "queued", Job.run_at <= utcnow())
                        .order_by(Job.run_at).limit(1).with_for_update(skip_locked=True))
        if not job:
            return False
        job.status, job.locked_at, job.attempts = "running", utcnow(), job.attempts + 1
        db.commit()
        job_id, kind, payload, attempts, max_attempts = job.id, job.kind, dict(job.payload), job.attempts, job.max_attempts

    fn = HANDLERS.get(kind)
    try:
        if fn is None:
            raise RuntimeError(f"no handler registered for job kind {kind!r}")
        with SessionLocal() as db:
            fn(db, payload)
            db.commit()
    except Exception as e:  # noqa: BLE001 - every failure is recorded and retried or surfaced
        log.exception("job %s (%s) failed on attempt %s", job_id, kind, attempts)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.last_error = "".join(traceback.format_exception_only(e))[-2000:]
            if attempts >= max_attempts:
                job.status, job.finished_at = "dead", utcnow()
                alert(db, "job_failed", f"Background task '{kind}' failed permanently: {e}", severity="error", ref=("job", job_id))
            else:
                job.status, job.run_at = "queued", utcnow() + backoff(attempts)
            db.commit()
        return True

    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job_id).values(status="done", finished_at=utcnow(), last_error=None))
        db.commit()
    return True


def requeue_stale() -> None:
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.status == "running", Job.locked_at < utcnow() - STALE_LOCK)
                   .values(status="queued", run_at=utcnow()))
        db.commit()


def schedule_periodic(now: datetime | None = None) -> None:
    now = now or utcnow()
    with SessionLocal() as db:
        for kind, (every, _) in PERIODIC.items():
            bucket = int(now.timestamp()) // every
            enqueue(db, kind, {}, dedupe_key=f"periodic:{kind}:{bucket}", max_attempts=1)
        db.commit()


def heartbeat(name: str) -> None:
    with SessionLocal() as db:
        db.merge(WorkerHeartbeat(name=name, beat_at=utcnow()))
        db.commit()


def drain(limit: int = 1000) -> int:
    """Run every due job now (tests and the CLI)."""
    n = 0
    while n < limit and run_one():
        n += 1
    return n


def worker_loop(poll_seconds: float = 1.0) -> None:  # pragma: no cover - long-running process
    from .. import registry  # noqa: F401  registers all handlers
    name = f"worker@{socket.gethostname()}"
    log.info("worker %s started with %d handlers", name, len(HANDLERS))
    last_maintenance = 0.0
    while True:
        if time.monotonic() - last_maintenance > 30:
            heartbeat(name)
            requeue_stale()
            schedule_periodic()
            last_maintenance = time.monotonic()
        if not run_one():
            time.sleep(poll_seconds)
