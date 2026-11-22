"""Small admin commands.

.venv\\Scripts\\python -m app.cli seed-demo     # demo organization + n8n service key (idempotent)
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


COMMANDS = {"seed-demo": seed_demo}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print("Commands: " + ", ".join(COMMANDS))
        sys.exit(2)
    sys.exit(COMMANDS[cmd]())
