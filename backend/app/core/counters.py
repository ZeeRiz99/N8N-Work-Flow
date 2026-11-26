"""Counters shared by every backend worker and CLI process, kept in PostgreSQL.

- `take_slot`: an atomic "increment unless the limit is reached" (the daily Gemini budget).
- `hit`: a sliding-window rate limit; requests for one key are serialized with a transaction
  advisory lock, so two workers can never both let the 11th request through.

Each call uses its own short transaction (not the request's session), so a counted request
stays counted even when the request itself fails, e.g. a wrong password.
"""

import random

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_session_factory

_TAKE = text(
    """
    INSERT INTO usage_counters (scope, period, key, count)
    VALUES (:scope, :period, :key, 1)
    ON CONFLICT (scope, period, key) DO UPDATE
       SET count = usage_counters.count + 1, updated_at = now()
     WHERE usage_counters.count < :limit
    RETURNING count
    """
)
_SET = text(
    """
    INSERT INTO usage_counters (scope, period, key, count)
    VALUES (:scope, :period, :key, :count)
    ON CONFLICT (scope, period, key) DO UPDATE SET count = :count, updated_at = now()
    """
)


def _factory(factory: sessionmaker[Session] | None) -> sessionmaker[Session]:
    return factory or get_session_factory()


def take_slot(
    scope: str, period: str, key: str, limit: int, factory: sessionmaker[Session] | None = None
) -> bool:
    """Reserve one unit. False when `limit` units are already taken for this period."""
    if limit <= 0:
        return False
    with _factory(factory)() as s:
        row = s.execute(
            _TAKE, {"scope": scope, "period": period, "key": key, "limit": limit}
        ).first()
        s.commit()
        return row is not None


def get_count(
    scope: str, period: str, key: str, factory: sessionmaker[Session] | None = None
) -> int:
    with _factory(factory)() as s:
        n = s.execute(
            text(
                "SELECT count FROM usage_counters WHERE scope = :scope AND period = :period"
                " AND key = :key"
            ),
            {"scope": scope, "period": period, "key": key},
        ).scalar()
        return int(n or 0)


def set_count(
    scope: str, period: str, key: str, count: int, factory: sessionmaker[Session] | None = None
) -> None:
    with _factory(factory)() as s:
        s.execute(_SET, {"scope": scope, "period": period, "key": key, "count": count})
        s.commit()


def hit(
    key: str, limit: int, window_seconds: float, factory: sessionmaker[Session] | None = None
) -> bool:
    """Count one request for `key`; False (and not counted) when the window is full."""
    with _factory(factory)() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
        n = s.execute(
            text(
                "SELECT count(*) FROM rate_limit_hits"
                " WHERE key = :k AND at > now() - make_interval(secs => :w)"
            ),
            {"k": key, "w": window_seconds},
        ).scalar()
        if int(n or 0) >= limit:
            s.commit()
            return False
        s.execute(text("INSERT INTO rate_limit_hits (key) VALUES (:k)"), {"k": key})
        if random.random() < 0.01:  # noqa: S311 - housekeeping sample, not security
            s.execute(text("DELETE FROM rate_limit_hits WHERE at < now() - interval '1 hour'"))
        s.commit()
        return True
