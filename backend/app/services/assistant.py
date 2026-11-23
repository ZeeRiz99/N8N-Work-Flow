"""AI Assistant features (master prompt §8.5, §10 item 7): Lead Q&A, the text playground,
follow-up eligibility, and per-organization AI settings. None of them can send or change
anything except the activity log."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.keyword_qa import keyword_answer
from app.ai.pipeline import LeadFacts, assess, prepare
from app.ai.prompts import analysis_v1, qa_v1
from app.ai.provider import AIInvalidOutput, AIUnavailable
from app.ai.schemas import QAOutput
from app.core.config import get_settings
from app.models import (
    Lead,
    LeadActivity,
    LeadInquiry,
    LeadNote,
    Organization,
    PipelineStage,
)
from app.services.activity import record
from app.services.analysis import _catalog, _provider_or_error, active_config, latest

# ---------------------------------------------------------------- AI settings

STYLES = ("professional", "friendly", "concise", "sales")


def ai_settings(org: Organization) -> dict:
    s = (org.settings or {}).get("ai", {})
    server_cap = get_settings().ai_daily_call_cap
    return {
        "default_style": s.get("default_style", "professional"),
        "daily_cap": min(int(s.get("daily_cap", server_cap)), server_cap),
        "server_max_daily_cap": server_cap,
        "provider": get_settings().ai_provider,
        "model": get_settings().gemini_models[0]
        if get_settings().ai_provider == "gemini"
        else "offline",
    }


def save_ai_settings(org: Organization, default_style: str, daily_cap: int) -> dict:
    if default_style not in STYLES:
        raise ValueError("Unknown style.")
    server_cap = get_settings().ai_daily_call_cap
    if not 0 <= daily_cap <= server_cap:
        raise ValueError(f"The daily limit must be between 0 and {server_cap}.")
    settings = dict(org.settings or {})
    settings["ai"] = {"default_style": default_style, "daily_cap": daily_cap}
    org.settings = settings
    return ai_settings(org)


# ---------------------------------------------------------------- Lead Q&A


def lead_records(db: Session, lead: Lead) -> dict:
    """Only this lead's own records, each with an id the answer can cite."""
    inquiries = db.scalars(
        select(LeadInquiry).where(LeadInquiry.lead_id == lead.id).order_by(LeadInquiry.received_at)
    ).all()
    notes = db.scalars(
        select(LeadNote).where(LeadNote.lead_id == lead.id).order_by(LeadNote.created_at)
    ).all()
    acts = db.scalars(
        select(LeadActivity)
        .where(LeadActivity.lead_id == lead.id)
        .order_by(LeadActivity.created_at.desc())
        .limit(30)
    ).all()
    a, s = latest(db, lead.id)
    analysis = []
    if a is not None and a.status == "done":
        analysis.append(
            {
                "id": str(a.id),
                "summary": a.summary,
                "facts": (a.extracted or {}).get("grounded", {}),
                "intent": (a.assessment or {}).get("intent"),
            }
        )
    if s is not None:
        analysis.append({"id": str(s.id), "score": s.total, "band": s.band, "text": s.explanation})
    return {
        "lead": {
            "id": str(lead.id),
            "name": lead.full_name,
            "company": lead.company,
            "email": lead.email,
            "phone": lead.phone_raw,
            "created": lead.created_at,
        },
        "inquiries": [
            {
                "id": str(i.id),
                "received": i.received_at,
                "channel": i.channel,
                "message": i.message,
                "form": i.form_fields,
            }
            for i in inquiries
        ],
        "notes": [{"id": str(n.id), "written": n.created_at, "body": n.body} for n in notes],
        "activities": [
            {"id": str(x.id), "at": x.created_at, "type": x.type, "details": x.payload}
            for x in acts
        ],
        "analysis": analysis,
    }


def ask(
    db: Session, org_id: uuid.UUID, lead: Lead, question: str, actor_id: uuid.UUID | None
) -> dict:
    records = lead_records(db, lead)
    valid_ids = {records["lead"]["id"]} | {
        r["id"] for g in ("inquiries", "notes", "activities", "analysis") for r in records[g]
    }
    provider = _provider_or_error()
    source, model, note = "keyword", None, None
    out: QAOutput | None = None
    if isinstance(provider, str):
        note = "AI unavailable; showing records that mention your words."
    else:
        try:
            r = provider.generate(qa_v1.SYSTEM, qa_v1.build_user(question, records), QAOutput)
            out, source, model = r.output, r.provider, r.model
        except (AIUnavailable, AIInvalidOutput):
            note = "AI unavailable; showing records that mention your words."
    if out is None:
        out = keyword_answer(question, records)
    cited = [c for c in out.citations if c in valid_ids]
    invented = [c for c in out.citations if c not in valid_ids]
    supported = out.refused or bool(cited) or "do not" in out.answer.lower()
    record(db, org_id, lead.id, "question_asked", "user", actor_id, source=source)
    db.commit()
    by_id = {
        r["id"]: (g, r)
        for g in ("inquiries", "notes", "activities", "analysis")
        for r in records[g]
    }
    return {
        "answer": out.answer,
        "refused": out.refused,
        "citations": [
            {
                "id": c,
                "kind": by_id[c][0].rstrip("s") if c in by_id else "lead",
                "label": _label(by_id.get(c)),
            }
            for c in cited
        ],
        "removed_citations": len(invented),
        "supported": supported,
        "source": source,
        "model": model,
        "note": note,
    }


def _label(item) -> str:
    if not item:
        return "Lead details"
    group, r = item
    when = r.get("received") or r.get("written") or r.get("at")
    day = when.strftime("%b %d") if hasattr(when, "strftime") else ""
    return {
        "inquiries": f"Message, {day}",
        "notes": f"Note, {day}",
        "activities": f"{str(r.get('type', '')).replace('_', ' ').capitalize()}, {day}",
        "analysis": "AI analysis" if "summary" in r else "Score",
    }[group]


# ---------------------------------------------------------------- playground


def analyze_text(db: Session, org_id: uuid.UUID, message: str, form: dict | None = None) -> dict:
    """Analyze pasted text with the org's catalog and scoring. Nothing is saved."""
    org = db.get(Organization, org_id)
    catalog = _catalog(db, org_id)
    cfg = active_config(db, org_id)
    prep = prepare(message, form or {}, catalog, org.name)
    provider = _provider_or_error()
    out, source, model, note = None, None, None, None
    if not prep.has_text:
        note = "Paste a message to analyze."
    elif isinstance(provider, str):
        note = f"AI unavailable ({provider}); provisional score only."
    else:
        try:
            r = provider.analyze(analysis_v1.SYSTEM, prep.user_prompt)
            out, source, model = r.output, r.provider, r.model
        except (AIUnavailable, AIInvalidOutput) as exc:
            note = f"AI unavailable ({str(exc)[:80]}); provisional score only."
    done = assess(
        out,
        prep,
        form or {},
        catalog,
        org.currency or "USD",
        LeadFacts(None, None, None, None),
        cfg.weights,
        cfg.thresholds,
        cfg.ideal_customer,
    )
    res = done.result
    return {
        "facts": done.grounded.as_dict(),
        "intent": out.assessment.intent if out else None,
        "summary": out.assessment.summary if out else None,
        "guard_flags": prep.guard.flags,
        "score": {
            "total": res.total,
            "band": res.band,
            "explanation": res.explanation,
            "factors": [dict(f.__dict__) for f in res.factors],
            "caps": res.caps,
            "provisional": res.provisional,
        },
        "needs_review": done.needs_review,
        "source": source,
        "model": model,
        "note": note,
        "saved": False,
    }


# ---------------------------------------------------------------- follow-up suggestion

MAX_FOLLOW_UPS = 3
COOLDOWN_DAYS = 3


def follow_up_status(db: Session, lead: Lead, now: datetime | None = None) -> dict:
    """Whether to follow up is decided here, in code (§8.5). The AI only writes the wording."""
    now = now or datetime.now(UTC)
    stage = db.get(PipelineStage, lead.stage_id) if lead.stage_id else None
    sent = (
        db.scalar(
            select(func.count())
            .select_from(LeadActivity)
            .where(LeadActivity.lead_id == lead.id, LeadActivity.type == "follow_up_drafted")
        )
        or 0
    )
    last = lead.last_interaction_at
    days = (now - last).days if last else None
    checks = [
        ("open", "Lead is in an open stage", stage is None or stage.category == "open"),
        ("contactable", "Not marked do not contact", not lead.do_not_contact),
        ("email", "Has an email address", bool(lead.email)),
        (
            "attempts",
            f"Fewer than {MAX_FOLLOW_UPS} follow-ups so far ({sent})",
            sent < MAX_FOLLOW_UPS,
        ),
        (
            "cooldown",
            f"At least {COOLDOWN_DAYS} days since the last contact"
            + (f" ({days} days)" if days is not None else ""),
            days is None or days >= COOLDOWN_DAYS,
        ),
    ]
    return {
        "eligible": all(ok for _, _, ok in checks),
        "checks": [{"key": k, "label": label, "ok": ok} for k, label, ok in checks],
        "next_possible": (last + timedelta(days=COOLDOWN_DAYS)).isoformat()
        if last and days is not None and days < COOLDOWN_DAYS
        else None,
        "replies_tracked": False,  # inbound replies are not recorded yet
    }
