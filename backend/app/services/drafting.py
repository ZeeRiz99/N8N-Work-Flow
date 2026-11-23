"""Reply drafting (master prompt §8.4). Builds the allowed input, asks the provider, falls back
to a code template when the AI is unavailable, then runs the code checks.

P5 returns the draft as a preview. Saving, approval and sending arrive in P6
(communication_drafts); nothing here can send anything.
"""

import uuid
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.draft_checks import finalize_body, passed, run_checks
from app.ai.draft_template import template_draft
from app.ai.prompts import draft_v1
from app.ai.provider import AIInvalidOutput, AIProvider, AIUnavailable
from app.ai.schemas import DraftOutput
from app.core.config import get_settings
from app.models import Lead, Organization
from app.services.activity import record
from app.services.analysis import _catalog, _provider_or_error, latest

NO_DRAFT_INTENTS = {"spam": "it looks like spam", "job_seeker": "it is a job application"}


class DraftRefused(Exception):
    """No draft should be written for this lead (spam, job seeker)."""


def allowed_domains(org: Organization, lead: Lead) -> set[str]:
    domains = set()
    for url in (org.settings or {}).get("website"), get_settings().frontend_public_url:
        if url:
            host = urlparse(url if "://" in url else f"https://{url}").hostname
            if host:
                domains.add(host.removeprefix("www."))
    return domains


_QUESTION_KEYS = {
    "phone": "phone",
    "phone number": "phone",
    "contact number": "phone",
    "name": "name",
    "contact name": "name",
    "full name": "name",
    "email": "email",
    "email address": "email",
    "company": "company",
    "company name": "company",
    "business name": "company",
    "budget": "budget",
    "timeline": "timeline",
    "deadline": "timeline",
}


def open_questions(missing: list[str], lead: Lead) -> list[str]:
    """The model's missing-info list, minus anything the lead record already has."""
    have = {
        "phone": bool(lead.phone_raw),
        "name": bool(lead.full_name),
        "email": bool(lead.email),
        "company": bool(lead.company),
    }
    out = []
    for item in missing:
        key = " ".join(str(item).lower().replace("_", " ").split())
        key = _QUESTION_KEYS.get(key, key)
        if key and not have.get(key, False) and key not in out:
            out.append(key)
    return out[:3]


def build_input(
    org: Organization, lead: Lead, facts: dict, catalog: list[dict], style: str, language: str
) -> dict:
    """Only allowed inputs (§8.4): no other leads, notes, scores or internal URLs."""
    wanted = [s["name"] for s in facts.get("services", []) if s.get("name") != "other"]
    services = [c for c in catalog if c["name"] in wanted][:3]
    settings = org.settings or {}
    return {
        "business": {
            "name": org.name,
            "response_time_line": settings.get("response_time_line"),
        },
        "customer": {"first_name": (lead.full_name or "").split(" ")[0][:40]},
        "style": style,
        "style_guide": draft_v1.STYLES[style],
        "language": language,
        "services": [
            {
                "name": s["name"],
                "price_min_minor": s["price_min_minor"],
                "price_max_minor": s["price_max_minor"],
                "currency": org.currency or "USD",
            }
            for s in services
        ],
        "facts": {
            "requirements": [r["text"] for r in facts.get("requirements", [])][:5],
            "timeline": (facts.get("timeline") or {}).get("text"),
            "budget_stated": bool(facts.get("budget")),
        },
        "open_questions": open_questions(facts.get("missing_info", []), lead),
    }


def generate_draft(
    db: Session,
    org_id: uuid.UUID,
    lead_id: uuid.UUID,
    style: str = "professional",
    actor_id: uuid.UUID | None = None,
    provider: AIProvider | None = None,
) -> dict | None:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id))
    if lead is None:
        return None
    org = db.get(Organization, org_id)
    analysis, _ = latest(db, lead.id)
    assessment = (analysis.assessment if analysis else {}) or {}
    intent = assessment.get("intent")
    if intent in NO_DRAFT_INTENTS:
        raise DraftRefused(f"No reply drafted: {NO_DRAFT_INTENTS[intent]}.")
    facts = ((analysis.extracted or {}).get("grounded", {}) if analysis else {}) or {}
    language = ((analysis.extracted or {}).get("raw", {}) if analysis else {}).get("language", "en")
    catalog = _catalog(db, org_id)
    data = build_input(org, lead, facts, catalog, style, language or "en")
    user = draft_v1.build_user(data)

    source, model, note = "template", None, None
    chosen = provider or _provider_or_error()
    out: DraftOutput | None = None
    if isinstance(chosen, str):
        note = f"AI unavailable ({chosen}); drafted from a template."
    else:
        try:
            r = chosen.generate(draft_v1.SYSTEM, user, DraftOutput, temperature=0.4)
            out, source, model = r.output, r.provider, r.model
        except (AIUnavailable, AIInvalidOutput) as exc:
            note = f"AI unavailable ({str(exc)[:80]}); drafted from a template."
    if out is None:
        out = template_draft(data)

    body = finalize_body(out.body)
    checks = run_checks(
        out.subject,
        body,
        out.services_mentioned,
        catalog,
        allowed_domains(org, lead),
        lead.do_not_contact,
        bool(lead.email),
        language or "en",
    )
    record(
        db,
        org_id,
        lead.id,
        "draft_generated",
        "user" if actor_id else "system",
        actor_id,
        style=style,
        source=source,
        checks_passed=passed(checks),
    )
    db.commit()
    return {
        "to": lead.email,  # read-only: always the lead's own address
        "subject": out.subject,
        "body": body,
        "questions": out.questions,
        "services_mentioned": out.services_mentioned,
        "style": style,
        "source": source,
        "model": model,
        "prompt_version": draft_v1.PROMPT_VERSION,
        "note": note,
        "checks": checks,
        "all_passed": passed(checks),
    }


def recheck(
    db: Session,
    org_id: uuid.UUID,
    lead_id: uuid.UUID,
    subject: str,
    body: str,
    services_mentioned: list[str],
) -> list[dict] | None:
    """Rerun the checks after a human edit (the opt-out line is re-appended by code)."""
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id))
    if lead is None:
        return None
    org = db.get(Organization, org_id)
    analysis, _ = latest(db, lead.id)
    language = ((analysis.extracted or {}).get("raw", {}) if analysis else {}).get("language", "en")
    return run_checks(
        subject,
        finalize_body(body),
        services_mentioned,
        _catalog(db, org_id),
        allowed_domains(org, lead),
        lead.do_not_contact,
        bool(lead.email),
        language or "en",
    )
