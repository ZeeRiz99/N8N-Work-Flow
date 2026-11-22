"""Organizations, users and API keys."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    public_form_key: Mapped[str] = mapped_column(String(64), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'UTC'"))
    default_country: Mapped[str] = mapped_column(String(2), server_default=text("'US'"))
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'USD'"))
    settings: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(Text)  # set in P4 (argon2id)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class ApiKey(IdMixin, TimestampMixin, Base):
    """Service and integration keys. Only a SHA-256 hash is stored; the key is shown once."""

    __tablename__ = "api_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(40)), server_default=text("'{}'"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
