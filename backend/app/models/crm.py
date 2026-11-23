"""Per-organization CRM configuration: pipeline stages, lead sources, service catalog."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

STAGE_CATEGORIES = ("open", "won", "lost")
SOURCE_KINDS = ("form", "api", "csv", "webhook", "telegram", "email", "manual")

DEFAULT_STAGES = [
    # (key, label, category) — keys of system stages never change; labels and order may.
    ("new", "New", "open"),
    ("ai_processed", "AI processed", "open"),
    ("qualified", "Qualified", "open"),
    ("contacted", "Contacted", "open"),
    ("meeting_scheduled", "Meeting scheduled", "open"),
    ("proposal_sent", "Proposal sent", "open"),
    ("won", "Won", "won"),
    ("lost", "Lost", "lost"),
]
DEFAULT_SOURCES = [
    ("form", "Web form", "form"),
    ("api", "API", "api"),
    ("csv", "CSV import", "csv"),
    ("webhook", "Other tools (webhook)", "webhook"),
    ("email", "Email", "email"),
    ("manual", "Added by hand", "manual"),
]


class PipelineStage(IdMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        Index("ix_pipeline_stages_org_position", "organization_id", "position"),
        CheckConstraint(f"category IN {STAGE_CATEGORIES}", name="category_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column()
    category: Mapped[str] = mapped_column(String(10), server_default=text("'open'"))
    is_system: Mapped[bool] = mapped_column(server_default=text("false"))


class LeadSource(IdMixin, TimestampMixin, Base):
    __tablename__ = "lead_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(f"kind IN {SOURCE_KINDS}", name="kind_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(12))


class Service(IdMixin, TimestampMixin, Base):
    """What the business sells. Powers service relevance, budget fit and reply drafts (P5)."""

    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        CheckConstraint(
            "price_min_minor IS NULL OR price_max_minor IS NULL "
            "OR price_min_minor <= price_max_minor",
            name="price_range_valid",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String(60)), server_default=text("'{}'"))
    price_min_minor: Mapped[int | None] = mapped_column()
    price_max_minor: Mapped[int | None] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'USD'"))
    active: Mapped[bool] = mapped_column(server_default=text("true"))
