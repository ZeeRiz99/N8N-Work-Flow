"""Shared FastAPI dependencies: service-key auth, temporary dev access, rate limiting."""

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_key
from app.models import ApiKey, Organization

DbSession = Annotated[Session, Depends(get_db)]


def require_service_key(
    db: DbSession, x_service_key: Annotated[str | None, Header()] = None
) -> Organization:
    """n8n -> /internal/*: a hashed, revocable key with the 'internal' scope."""
    if not x_service_key:
        raise HTTPException(401, "Missing service key.")
    key = db.scalar(
        select(ApiKey).where(
            ApiKey.key_hash == hash_key(x_service_key), ApiKey.revoked_at.is_(None)
        )
    )
    if key is None or "internal" not in (key.scopes or []):
        raise HTTPException(401, "Invalid service key.")
    key.last_used_at = datetime.now(UTC)
    db.commit()
    org = db.get(Organization, key.organization_id)
    if org is None:
        raise HTTPException(401, "Invalid service key.")
    return org


ServiceOrg = Annotated[Organization, Depends(require_service_key)]


def require_dev_access(request: Request, db: DbSession) -> Organization:
    """TEMPORARY (P3 only): dashboard reads for the demo org, from this machine, in development.

    Replaced by real login and roles in P4. Never enabled outside APP_ENV=development.
    """
    settings = get_settings()
    client_host = request.client.host if request.client else ""
    if settings.app_env != "development" or client_host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Dashboard access needs login (coming in Phase 4).")
    org = db.scalar(select(Organization).where(Organization.slug == settings.demo_org_slug))
    if org is None:
        raise HTTPException(404, "Demo organization not found. Run the seed command.")
    return org


DevOrg = Annotated[Organization, Depends(require_dev_access)]


class RateLimiter:
    """In-memory sliding window per client IP. Fine for one dev process; P10 hardens it."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


public_form_limiter = RateLimiter()


def public_form_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not public_form_limiter.check(ip, get_settings().public_form_rate_limit_per_minute):
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
