from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor_type: Mapped[str] = mapped_column(String(16))  # staff | system | ai | customer | provider
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)


class Alert(Base):
    """Staff-visible problems and events that need a human (handoffs, failures, AI outages)."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info | warning | error
    message: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime | None]
    acknowledged_by: Mapped[int | None] = mapped_column(Integer)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    quantity: Mapped[int] = mapped_column(BigInteger, default=1)
    cost_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IntegrationStatus(Base):
    __tablename__ = "integration_status"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_success_at: Mapped[datetime | None]
    last_failure_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    """Postgres-backed job queue. Jobs are inserted in the same transaction as the business change
    that needs them (transactional outbox), so a booking can never exist without its reminder job."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    run_at: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | dead | cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=6)
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    locked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]

    __table_args__ = (Index("ix_jobs_ready", "status", "run_at"),)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    beat_at: Mapped[datetime] = mapped_column(default=utcnow)


class WebhookEvent(Base):
    """Every provider webhook delivery, deduplicated by the provider's event id."""
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    processed_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(16), default="received")  # received | processed | ignored | failed
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)
