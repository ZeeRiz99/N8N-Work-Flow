"""Idempotency keys, the transactional outbox, n8n workflow runs and shared counters."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

OUTBOX_STATUSES = ("pending", "delivered", "failed")
RUN_STATUSES = ("running", "success", "failed", "retrying", "skipped")


class IdempotencyKey(IdMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("organization_id", "scope", "key"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(200))
    response: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(IdMixin, TimestampMixin, Base):
    """Written in the same transaction as the change it announces; dispatched afterwards."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_status_next_attempt", "status", "next_attempt_at"),
        CheckConstraint(f"status IN {OUTBOX_STATUSES}", name="status_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12), server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))


class WorkflowExecution(IdMixin, TimestampMixin, Base):
    """One n8n run, upserted by (workflow_key, n8n_execution_id).

    organization_id is nullable on purpose: the error workflow (W9, P6) may fail
    before it knows which organization a run belonged to.
    """

    __tablename__ = "workflow_executions"
    __table_args__ = (
        UniqueConstraint("workflow_key", "n8n_execution_id"),
        CheckConstraint(f"status IN {RUN_STATUSES}", name="status_valid"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workflow_key: Mapped[str] = mapped_column(String(40))
    n8n_execution_id: Mapped[str] = mapped_column(String(40))
    request_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(server_default=text("0"))
    meta: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class UsageCounter(Base):
    """A counter shared by every process: e.g. the daily Gemini budget (scope "ai_budget",
    period = the quota day, key = provider). Incremented atomically with a guarded upsert."""

    __tablename__ = "usage_counters"

    scope: Mapped[str] = mapped_column(String(40), primary_key=True)
    period: Mapped[str] = mapped_column(String(40), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RateLimitHit(Base):
    """One request counted by a rate limiter (sliding window shared by all workers)."""

    __tablename__ = "rate_limit_hits"
    __table_args__ = (
        Index("ix_rate_limit_hits_key_at", "key", "at"),
        Index("ix_rate_limit_hits_at", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
