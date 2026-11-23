"""Reply drafts, the communication log and basic follow-ups (master prompt §6, P6).

Nothing is ever sent unless a draft is `approved` by a person; the send path claims it
atomically (approved -> sending) so a redelivered event cannot send twice.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

DRAFT_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "rejected",
    "sending",
    "sent",
    "failed",
    "cancelled",
)
DRAFT_KINDS = ("first_reply", "follow_up", "recovery")
FOLLOW_UP_STATUSES = ("scheduled", "awaiting_approval", "done", "skipped", "cancelled")


class CommunicationDraft(IdMixin, TimestampMixin, Base):
    __tablename__ = "communication_drafts"
    __table_args__ = (
        Index("ix_communication_drafts_org_status", "organization_id", "status"),
        Index("ix_communication_drafts_lead", "lead_id"),
        CheckConstraint(f"status IN {DRAFT_STATUSES}", name="status_valid"),
        CheckConstraint(f"kind IN {DRAFT_KINDS}", name="kind_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_analyses.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(20), server_default=text("'email'"))
    kind: Mapped[str] = mapped_column(String(12), server_default=text("'first_reply'"))
    to_address: Mapped[str | None] = mapped_column(String(320))  # copied from the lead, read-only
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    style: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending_approval'"))
    checks: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    services_mentioned: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    source: Mapped[str] = mapped_column(String(20))  # gemini | fake | template
    model: Mapped[str | None] = mapped_column(String(60))
    edited: Mapped[bool] = mapped_column(server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_error: Mapped[str | None] = mapped_column(String(300))


class CommunicationLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "communication_logs"
    __table_args__ = (Index("ix_communication_logs_lead", "lead_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communication_drafts.id", ondelete="SET NULL")
    )
    direction: Mapped[str] = mapped_column(String(3))  # out | in
    channel: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(300))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FollowUp(IdMixin, TimestampMixin, Base):
    __tablename__ = "follow_ups"
    __table_args__ = (
        Index("ix_follow_ups_org_status_due", "organization_id", "status", "due_at"),
        CheckConstraint(f"status IN {FOLLOW_UP_STATUSES}", name="status_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(20), server_default=text("'follow_up'"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'scheduled'"))
    skip_reason: Mapped[str | None] = mapped_column(String(200))
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communication_drafts.id", ondelete="SET NULL")
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempt_no: Mapped[int] = mapped_column(server_default=text("1"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


SUPPRESSION_REASONS = ("unsubscribed", "replied", "bounced", "manual")


class Suppression(IdMixin, TimestampMixin, Base):
    """Addresses that must not be contacted (master prompt §6). Every send path checks it."""

    __tablename__ = "suppressions"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "address_normalized"),
        CheckConstraint(f"reason IN {SUPPRESSION_REASONS}", name="reason_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    channel: Mapped[str] = mapped_column(String(20), server_default=text("'email'"))
    address_normalized: Mapped[str] = mapped_column(String(320))
    reason: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
