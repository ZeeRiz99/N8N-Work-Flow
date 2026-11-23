"""Shared FastAPI dependencies: users and roles, service-key auth, CSRF, client IP, rate limits."""

import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_key
from app.models import ApiKey, Organization, OrganizationMember, User
from app.services.auth import AuthError, decode_access_token

DbSession = Annotated[Session, Depends(get_db)]
ACCESS_COOKIE = "rl_access"
REFRESH_COOKIE = "rl_refresh"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "replyline"
ROLE_RANK = {"member": 1, "admin": 2, "owner": 3}
LOCAL_PROXIES = {"127.0.0.1", "::1"}


# ---------------------------------------------------------------- client IP


def client_ip(request: Request) -> str:
    """The visitor's IP. X-Forwarded-For is trusted only when the direct peer is the local
    Next.js proxy; from anywhere else it could be forged."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if peer in LOCAL_PROXIES and forwarded:
        return forwarded.split(",")[0].strip() or peer
    return peer


# ---------------------------------------------------------------- users


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    email: str
    full_name: str

    def at_least(self, role: str) -> bool:
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK[role]


def require_user(request: Request, db: DbSession) -> CurrentUser:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(401, "Please log in.")
    try:
        claims = decode_access_token(get_settings(), token)
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    user_id, org_id = uuid.UUID(claims["sub"]), uuid.UUID(claims["org"])
    # Re-check membership and role on every request, so a removed or demoted member loses access
    # immediately instead of when the 15-minute token expires.
    row = db.execute(
        select(User, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(User.id == user_id, OrganizationMember.organization_id == org_id)
    ).first()
    if row is None or not row[0].is_active:
        raise HTTPException(401, "Please log in.")
    user, role = row
    return CurrentUser(user.id, org_id, role, user.email, user.full_name)


UserDep = Annotated[CurrentUser, Depends(require_user)]


def require_role(role: str) -> Callable[[CurrentUser], CurrentUser]:
    def check(user: UserDep) -> CurrentUser:
        if not user.at_least(role):
            raise HTTPException(403, "Your role does not allow this action.")
        return user

    return check


AdminDep = Annotated[CurrentUser, Depends(require_role("admin"))]
OwnerDep = Annotated[CurrentUser, Depends(require_role("owner"))]


def csrf_protect(request: Request) -> None:
    """State-changing cookie requests need a custom header (browsers cannot add it cross-site
    without a CORS preflight, which only our own origin passes) and, if sent, a known Origin."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "Missing request header.")
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origin_list:
        raise HTTPException(403, "Request origin not allowed.")


# ---------------------------------------------------------------- service key (n8n)


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


# ---------------------------------------------------------------- rate limits


class RateLimiter:
    """In-memory sliding window per key. Fine for one dev process; P10 hardens it (backlog #14)."""

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
login_limiter = RateLimiter()


def public_form_rate_limit(request: Request) -> None:
    if not public_form_limiter.check(
        client_ip(request), get_settings().public_form_rate_limit_per_minute
    ):
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")


def login_rate_limit(request: Request) -> None:
    if not login_limiter.check(client_ip(request), get_settings().login_rate_limit_per_minute):
        raise HTTPException(429, "Too many login attempts. Please wait a minute and try again.")
