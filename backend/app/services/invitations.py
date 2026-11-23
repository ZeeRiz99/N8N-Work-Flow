"""Team invitations (P9). The token is shown once (link + email); only its hash is stored.
Accepting creates the account (or uses the existing one, after its password is verified) and
adds the membership with the invited role."""

import secrets
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_key
from app.models import Invitation, Organization, OrganizationMember, User
from app.services.activity import audit
from app.services.auth import AuthError, hash_password, password_problems, verify_password

VALID_DAYS = 7
INVITABLE = {"member", "admin"}  # ownership is granted later by an owner, never by invite


class InviteError(Exception):
    pass


def create(
    db: Session, org: Organization, email: str, role: str, actor_id: uuid.UUID
) -> tuple[Invitation, str]:
    email = email.strip().lower()
    if role not in INVITABLE:
        raise InviteError("Invite as a member or an admin.")
    member = db.scalar(
        select(OrganizationMember.id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org.id, User.email == email)
    )
    if member:
        raise InviteError("This person is already in your team.")
    now = datetime.now(UTC)
    for old in db.scalars(
        select(Invitation).where(
            Invitation.organization_id == org.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ):
        old.revoked_at = now  # one open invitation per address
    token = secrets.token_urlsafe(32)
    inv = Invitation(
        organization_id=org.id,
        email=email,
        role=role,
        token_hash=hash_key(token),
        invited_by=actor_id,
        expires_at=now + timedelta(days=VALID_DAYS),
    )
    db.add(inv)
    db.flush()
    audit(db, org.id, actor_id, "member.invited", "invitation", inv.id, email=email, role=role)
    return inv, token


def link(token: str) -> str:
    return f"{get_settings().frontend_public_url.rstrip('/')}/invite/{token}"


def send_email(org: Organization, email: str, token: str) -> bool:
    """Best effort (Mailpit in development). The link is also shown to the inviter."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = "Replyline <no-reply@replyline.local>"
    msg["To"] = email
    msg["Subject"] = f"You're invited to {org.name} on Replyline"
    msg.set_content(
        f"You have been invited to join {org.name} on Replyline.\n\n"
        f"Accept the invitation (valid for {VALID_DAYS} days):\n{link(token)}\n\n"
        "If you did not expect this, ignore this email."
    )
    try:
        with smtplib.SMTP(s.smtp_test_host, s.smtp_test_port, timeout=5) as smtp:
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        return False


def find(db: Session, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_key(token)))
    now = datetime.now(UTC)
    if inv is None or inv.revoked_at or inv.accepted_at:
        raise InviteError("This invitation is no longer valid.")
    if inv.expires_at < now:
        raise InviteError("This invitation has expired. Ask for a new one.")
    return inv


def accept(db: Session, token: str, full_name: str, password: str) -> tuple[User, Invitation]:
    inv = find(db, token)
    user = db.scalar(select(User).where(User.email == inv.email))
    if user is None:
        problems = password_problems(password)
        if problems:
            raise InviteError(" ".join(problems))
        user = User(
            email=inv.email,
            full_name=full_name.strip() or inv.email.split("@")[0],
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(user.password_hash, password):
        raise InviteError("You already have an account: enter its password to join.")
    db.add(OrganizationMember(organization_id=inv.organization_id, user_id=user.id, role=inv.role))
    inv.accepted_at = datetime.now(UTC)
    audit(db, inv.organization_id, user.id, "member.joined", "invitation", inv.id, role=inv.role)
    return user, inv


__all__ = ["AuthError", "InviteError", "accept", "create", "find", "link", "send_email"]
