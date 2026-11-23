"""Declarative base, naming conventions and shared columns."""

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


_clock_lock = threading.Lock()
_last_ts: datetime | None = None


def utcnow() -> datetime:
    """Strictly increasing UTC time for row timestamps. Postgres now() is the transaction start,
    so rows written in one transaction would tie and "latest" queries would pick at random."""
    global _last_ts
    with _clock_lock:
        t = datetime.now(UTC)
        if _last_ts is not None and t <= _last_ts:
            t = _last_ts + timedelta(microseconds=1)
        _last_ts = t
        return t


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
