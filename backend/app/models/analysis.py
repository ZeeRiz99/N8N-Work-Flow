"""AI analyses, score history and per-organization scoring configuration (master prompt §6, §8)."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

ANALYSIS_STATUSES = ("done", "failed", "skipped")


class LeadAnalysis(IdMixin, TimestampMixin, Base):
    """One model run on one inquiry. Stores what was asked (hash, versions) and what came back,
    so results are reproducible and unchanged inquiries are never re-analyzed (cache)."""

    __tablename__ = "lead_analyses"
    __table_args__ = (
        Index("ix_lead_analyses_lead_created", "lead_id", "created_at"),
        Index("ix_lead_analyses_org_hash", "organization_id", "input_hash"),
        CheckConstraint(f"status IN {ANALYSIS_STATUSES}", name="status_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_inquiries.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str] = mapped_column(String(20))
    schema_version: Mapped[str] = mapped_column(String(20))
    input_hash: Mapped[str] = mapped_column(String(64))
    extracted: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    assessment: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    guard: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    summary: Mapped[str | None] = mapped_column(Text)
    recommended_next_action: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(String(200))
    latency_ms: Mapped[int | None] = mapped_column()
    input_tokens: Mapped[int | None] = mapped_column()
    output_tokens: Mapped[int | None] = mapped_column()


class LeadScore(IdMixin, TimestampMixin, Base):
    """A score with its factor-by-factor breakdown. History is kept; the lead row holds the
    latest. config_version records which weights produced it (changing weights never rewrites
    old scores silently)."""

    __tablename__ = "lead_scores"
    __table_args__ = (Index("ix_lead_scores_lead_created", "lead_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_analyses.id", ondelete="SET NULL")
    )
    total: Mapped[int] = mapped_column()
    band: Mapped[str] = mapped_column(String(10))
    breakdown: Mapped[list] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    caps: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    config_version: Mapped[int] = mapped_column()
    provisional: Mapped[bool] = mapped_column(server_default=text("false"))
    needs_review: Mapped[bool] = mapped_column(server_default=text("false"))


class ScoringConfig(IdMixin, TimestampMixin, Base):
    """Versioned weights and bands per organization. Exactly one active version per org."""

    __tablename__ = "scoring_configs"
    __table_args__ = (
        UniqueConstraint("organization_id", "version"),
        Index(
            "uq_scoring_configs_one_active",
            "organization_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column()
    weights: Mapped[dict] = mapped_column(JSONB)
    thresholds: Mapped[dict] = mapped_column(JSONB)
    ideal_customer: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
