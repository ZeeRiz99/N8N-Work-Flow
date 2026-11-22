"""Possible duplicates for human review. Uncertain matches are never merged automatically."""

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

DUPLICATE_STATUSES = ("open", "merged", "dismissed")


class DuplicateCandidate(IdMixin, TimestampMixin, Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        # lead_a_id < lead_b_id is enforced in code, so each pair appears once.
        UniqueConstraint("organization_id", "lead_a_id", "lead_b_id"),
        CheckConstraint(f"status IN {DUPLICATE_STATUSES}", name="status_valid"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lead_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    lead_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    confidence: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(10), server_default=text("'open'"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
