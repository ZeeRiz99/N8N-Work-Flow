"""Leads and their inquiries."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

PRIORITIES = ("high", "medium", "low", "unscored")
AI_STATUSES = ("pending", "processing", "done", "failed", "skipped")


class Lead(IdMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index(
            "uq_leads_org_email_active",
            "organization_id",
            "email_normalized",
            unique=True,
            postgresql_where=text("email_normalized IS NOT NULL AND archived_at IS NULL"),
        ),
        Index("ix_leads_org_priority_created", "organization_id", "priority", "created_at"),
        Index("ix_leads_org_stage", "organization_id", "stage_id"),
        Index("ix_leads_org_follow_up", "organization_id", "next_follow_up_at"),
        # Trigram search index (name, company, email) is created in the P4 migration by hand.
        CheckConstraint(f"priority IN {PRIORITIES}", name="priority_valid"),
        CheckConstraint(f"ai_status IN {AI_STATUSES}", name="ai_status_valid"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    phone_raw: Mapped[str | None] = mapped_column(String(40))
    phone_e164: Mapped[str | None] = mapped_column(String(20), index=True)
    company: Mapped[str | None] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(300))  # stored only, never fetched (SSRF)
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_stages.id", ondelete="SET NULL")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_sources.id", ondelete="SET NULL")
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    do_not_contact: Mapped[bool] = mapped_column(server_default=text("false"))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    custom_fields: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    priority: Mapped[str] = mapped_column(String(10), server_default=text("'unscored'"))
    score: Mapped[int | None] = mapped_column()
    score_provisional: Mapped[bool] = mapped_column(server_default=text("false"))
    score_source: Mapped[str | None] = mapped_column(String(20))  # "fake" in P3
    ai_status: Mapped[str] = mapped_column(String(12), server_default=text("'pending'"))
    first_inquiry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadInquiry(IdMixin, TimestampMixin, Base):
    """One message from a lead. A returning lead adds an inquiry instead of a duplicate lead."""

    __tablename__ = "lead_inquiries"
    __table_args__ = (Index("ix_lead_inquiries_lead_received", "lead_id", "received_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    message: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), server_default=text("'form'"))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    # Structured form fields (service, budget band, timeline); trusted facts, source "form".
    form_fields: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
