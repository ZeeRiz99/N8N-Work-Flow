"""Small admin commands.

.venv\\Scripts\\python -m app.cli seed-demo       # demo org + n8n service key (idempotent)
.venv\\Scripts\\python -m app.cli set-demo-owner  # your own owner login (asks; password hidden)
"""

import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.security import hash_key, key_prefix, new_public_form_key
from app.models import ApiKey, Organization

DEMO_SETTINGS = {
    "demo": True,
    "services": [
        "Website Development",
        "Booking System",
        "AI Chatbot",
        "Automation Setup",
        "Something else",
    ],
    "budget_options": [
        "Under $500",
        "$500 to $1,500",
        "$1,500 to $5,000",
        "Over $5,000",
        "Not sure yet",
    ],
    "timeline_options": ["Within 1 month", "1 to 3 months", "No fixed date"],
    "response_time_line": "We usually answer within one business day.",
    "reply_target_minutes": 120,
}


def seed_demo() -> int:
    settings = get_settings()
    with get_session_factory()() as db:
        org = db.scalar(select(Organization).where(Organization.slug == settings.demo_org_slug))
        if org is None:
            org = Organization(
                name="Harbor Web Studio",
                slug=settings.demo_org_slug,
                public_form_key=new_public_form_key(),
                timezone="Asia/Karachi",
                default_country="US",
                currency="USD",
                settings=DEMO_SETTINGS,
            )
            db.add(org)
            db.flush()
            print(f"Created demo organization '{org.name}' ({org.slug}). Demo data, fictional.")
        else:
            print(f"Demo organization '{org.name}' already exists.")

        if not settings.service_api_key:
            print("SERVICE_API_KEY is empty in .env; skipped the n8n service key.")
        else:
            digest = hash_key(settings.service_api_key)
            existing = db.scalar(select(ApiKey).where(ApiKey.key_hash == digest))
            if existing is None:
                db.add(
                    ApiKey(
                        organization_id=org.id,
                        name="n8n service key",
                        prefix=key_prefix(settings.service_api_key),
                        key_hash=digest,
                        scopes=["internal"],
                    )
                )
                print("Registered the n8n service key (stored as a hash only).")
            else:
                print("n8n service key already registered.")
        db.commit()
        print(f"Public form: {settings.frontend_public_url.rstrip('/')}/f/{org.slug}")
    return 0


def set_demo_owner() -> int:
    """Create or update YOUR owner login for the demo organization. Asks interactively; the
    password is typed hidden and stored only as an argon2id hash."""
    import getpass

    from app.models import OrganizationMember, User
    from app.schemas.public import EMAIL_RE
    from app.services.auth import hash_password, password_problems

    settings = get_settings()
    email = input("Your email for logging in: ").strip()
    if not EMAIL_RE.match(email):
        print("That does not look like an email address. Nothing changed.")
        return 1
    name = input("Your name: ").strip() or email.split("@")[0]
    password = getpass.getpass("Choose a password (hidden): ")
    problems = password_problems(password)
    if problems:
        print("Password not accepted: " + " ".join(problems))
        return 1
    if getpass.getpass("Type it again (hidden): ") != password:
        print("The two passwords differ. Nothing changed.")
        return 1

    with get_session_factory()() as db:
        org = db.scalar(select(Organization).where(Organization.slug == settings.demo_org_slug))
        if org is None:
            print("Run seed-demo first.")
            return 1
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name)
            db.add(user)
        user.password_hash = hash_password(password)
        user.full_name = name
        db.flush()
        member = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id
            )
        )
        if member is None:
            db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"))
        else:
            member.role = "owner"
        db.commit()
    print(f"Done. Log in at {settings.frontend_public_url.rstrip('/')}/login as {email}.")
    return 0


COMMANDS = {"seed-demo": seed_demo, "set-demo-owner": set_demo_owner}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print("Commands: " + ", ".join(COMMANDS))
        sys.exit(2)
    sys.exit(COMMANDS[cmd]())
