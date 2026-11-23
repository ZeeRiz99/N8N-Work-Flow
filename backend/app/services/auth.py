"""Authentication (D7): argon2id passwords, 15-minute access JWT, rotating refresh tokens.

Refresh tokens are random, stored only as SHA-256 hashes, and grouped in families (one family
per login). Each refresh rotates the token. Presenting an already-rotated token means it leaked,
so the whole family is revoked and the user must log in again.
"""

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_key, new_public_form_key
from app.models import Organization, OrganizationMember, RefreshToken, User

_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters
# A real hash of a random password, so unknown emails cost the same time as wrong passwords.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))
JWT_ALG = "HS256"


class AuthError(Exception):
    """Login or token problem. The message is safe to show; it never says which part failed."""


@dataclass(frozen=True)
class Session_:
    access_token: str
    refresh_token: str
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("Use at least 10 characters.")
    if len(password) > 128:
        problems.append("Use at most 128 characters.")
    if password.lower() == password or password.upper() == password:
        problems.append("Mix upper and lower case letters.")
    if not re.search(r"\d", password):
        problems.append("Include at least one number.")
    return problems


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "org")[:60]


def _access_token(settings: Settings, user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, _secret(settings), algorithm=JWT_ALG)


def _secret(settings: Settings) -> str:
    if len(settings.app_secret_key) < 32:
        raise RuntimeError("APP_SECRET_KEY must be set (32+ characters). Run scripts/new-env.ps1.")
    return settings.app_secret_key


def decode_access_token(settings: Settings, token: str) -> dict:
    try:
        claims = jwt.decode(token, _secret(settings), algorithms=[JWT_ALG])
    except jwt.PyJWTError as exc:
        raise AuthError("Your session has expired. Please log in again.") from exc
    if claims.get("typ") != "access":
        raise AuthError("Your session has expired. Please log in again.")
    return claims


def _issue(
    db: Session,
    settings: Settings,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    family_id: uuid.UUID,
) -> tuple[Session_, RefreshToken]:
    raw = secrets.token_urlsafe(48)
    row = RefreshToken(
        user_id=user_id,
        organization_id=org_id,
        family_id=family_id,
        token_hash=hash_key(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
    )
    db.add(row)
    db.flush()
    return Session_(_access_token(settings, user_id, org_id, role), raw, user_id, org_id, role), row


def register(
    db: Session, settings: Settings, org_name: str, full_name: str, email: str, password: str
) -> Session_:
    if db.scalar(select(User.id).where(User.email == email)):
        raise AuthError("An account with this email already exists. Please log in.")
    base = slugify(org_name)
    slug, n = base, 1
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    org = Organization(name=org_name, slug=slug, public_form_key=new_public_form_key())
    user = User(email=email, full_name=full_name, password_hash=hash_password(password))
    db.add_all([org, user])
    db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"))
    from app.services.org import provision_defaults

    provision_defaults(db, org.id)
    user.last_login_at = datetime.now(UTC)
    session, _ = _issue(db, settings, user.id, org.id, "owner", uuid.uuid4())
    db.commit()
    return session


def login(db: Session, settings: Settings, email: str, password: str) -> Session_:
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else None, password)
    if not ok or user is None or not user.is_active:
        raise AuthError("Email or password is incorrect.")
    member = db.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at)
        .limit(1)
    )
    if member is None:
        raise AuthError("This account is not part of any organization yet.")
    if _hasher.check_needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    session, _ = _issue(db, settings, user.id, member.organization_id, member.role, uuid.uuid4())
    db.commit()
    return session


def refresh(db: Session, settings: Settings, raw_token: str) -> Session_:
    now = datetime.now(UTC)
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_key(raw_token)).with_for_update()
    )
    if row is None:
        raise AuthError("Your session has expired. Please log in again.")
    if row.revoked_at is not None:
        # Reuse of a rotated token: assume theft, end every session from this login.
        _revoke_family(db, row.family_id, now)
        db.commit()
        raise AuthError("Your session has expired. Please log in again.")
    if row.expires_at <= now:
        raise AuthError("Your session has expired. Please log in again.")
    member = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == row.user_id,
            OrganizationMember.organization_id == row.organization_id,
        )
    )
    user = db.get(User, row.user_id)
    if member is None or user is None or not user.is_active:
        _revoke_family(db, row.family_id, now)
        db.commit()
        raise AuthError("Your session has expired. Please log in again.")
    session, new_row = _issue(
        db, settings, row.user_id, row.organization_id, member.role, row.family_id
    )
    row.revoked_at, row.replaced_by_id = now, new_row.id
    db.commit()
    return session


def logout(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_key(raw_token)))
    if row is not None:
        _revoke_family(db, row.family_id, datetime.now(UTC))
        db.commit()


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
