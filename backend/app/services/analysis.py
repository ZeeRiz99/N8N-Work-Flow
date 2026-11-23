"""Analyze a lead (master prompt §8): guard -> cache -> provider -> ground -> score -> persist.

- The AI only extracts and judges; the score is computed by code from grounded facts.
- An unchanged inquiry (same input hash) reuses the stored model output, so it is never
  re-sent to the provider.
- If the provider fails (outage, circuit open, daily cap, bad output) the lead still gets a
  provisional score from trusted form choices and contact details, and ai_status "failed" so
  it can be re-run.
- Idempotent: analyzing a lead that is already done returns the stored result unless forced.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.fake_provider import FakeAIProvider
from app.ai.grounding import Grounded, ground
from app.ai.guard import screen
from app.ai.prompts import analysis_v1 as prompt
from app.ai.provider import AIInvalidOutput, AIProvider, AIResult, AIUnavailable
from app.ai.schemas import AnalysisOutput
from app.core.config import get_settings
from app.models import (
    Lead,
    LeadAnalysis,
    LeadInquiry,
    LeadScore,
    Organization,
    PipelineStage,
    ScoringConfig,
    Service,
)
from app.scoring.engine import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, ScoreInput, score
from app.services.activity import record

log = logging.getLogger(__name__)
CACHE_HIT = "cache hit"


def get_provider() -> AIProvider:
    s = get_settings()
    if s.ai_provider == "fake":
        return FakeAIProvider()
    from app.ai.gemini_provider import GeminiProvider  # the only SDK import site (D11)

    model, fallback = s.gemini_models
    return GeminiProvider(s.gemini_api_key, model, fallback, s.ai_timeout_seconds)


def _provider_or_error() -> AIProvider | str:
    try:
        return get_provider()
    except AIUnavailable as exc:
        return str(exc)[:200]


def active_config(db: Session, org_id: uuid.UUID) -> ScoringConfig:
    """The org's active scoring config; version 1 (the defaults) is created on first use."""
    cfg = db.scalar(
        select(ScoringConfig).where(
            ScoringConfig.organization_id == org_id, ScoringConfig.is_active.is_(True)
        )
    )
    if cfg is None:
        cfg = ScoringConfig(
            organization_id=org_id,
            version=1,
            weights=dict(DEFAULT_WEIGHTS),
            thresholds=dict(DEFAULT_THRESHOLDS),
            ideal_customer={},
            is_active=True,
        )
        db.add(cfg)
        db.flush()
    return cfg


def _calls_today(db: Session, org_id: uuid.UUID, provider: str) -> int:
    midnight = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return (
        db.scalar(
            select(func.count())
            .select_from(LeadAnalysis)
            .where(
                LeadAnalysis.organization_id == org_id,
                LeadAnalysis.provider == provider,
                LeadAnalysis.created_at >= midnight,
                LeadAnalysis.error.is_distinct_from(CACHE_HIT),
            )
        )
        or 0
    )


def _catalog(db: Session, org_id: uuid.UUID) -> list[dict]:
    services = db.scalars(
        select(Service).where(Service.organization_id == org_id, Service.active.is_(True))
    ).all()
    return [
        {
            "name": s.name,
            "keywords": list(s.keywords or []),
            "price_min_minor": s.price_min_minor,
            "price_max_minor": s.price_max_minor,
        }
        for s in services
    ]


def analyze_lead(
    db: Session, org_id: uuid.UUID, lead_id: uuid.UUID, force: bool = False
) -> dict | None:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id))
    if lead is None:
        return None
    if not force and lead.ai_status == "done" and lead.score is not None:
        return result_dict(db, lead)

    org = db.get(Organization, org_id)
    inquiry = db.scalar(
        select(LeadInquiry)
        .where(LeadInquiry.lead_id == lead.id, LeadInquiry.organization_id == org_id)
        .order_by(LeadInquiry.received_at.desc())
        .limit(1)
    )
    inquiry_count = (
        db.scalar(
            select(func.count()).select_from(LeadInquiry).where(LeadInquiry.lead_id == lead.id)
        )
        or 0
    )
    catalog = _catalog(db, org_id)
    cfg = active_config(db, org_id)
    lead.ai_status = "processing"
    db.flush()

    guard = screen(inquiry.message if inquiry else "")
    form = (inquiry.form_fields if inquiry else {}) or {}
    user = prompt.build_user(guard.text, form, [c["name"] for c in catalog], org.name)
    input_hash = hashlib.sha256(
        f"{prompt.PROMPT_VERSION}\n{prompt.SYSTEM}\n{user}".encode()
    ).hexdigest()
    has_text = bool(guard.text.strip())

    output: AnalysisOutput | None = None
    run: AIResult | None = None
    error: str | None = None
    provider = _provider_or_error()
    provider_name = provider.name if not isinstance(provider, str) else get_settings().ai_provider
    cached = db.scalar(
        select(LeadAnalysis)
        .where(
            LeadAnalysis.organization_id == org_id,
            LeadAnalysis.input_hash == input_hash,
            LeadAnalysis.provider == provider_name,  # never serve another provider's output
            LeadAnalysis.status == "done",
        )
        .order_by(LeadAnalysis.created_at.desc())
        .limit(1)
    )
    if not has_text:
        error = "no message to analyze"
    elif cached is not None:
        output = AnalysisOutput.model_validate(
            {"extraction": cached.extracted.get("raw", {}), "assessment": cached.assessment}
        )
        run = AIResult(output, cached.provider, cached.model or "", 0, 0, 0)
        error = CACHE_HIT
    elif isinstance(provider, str):
        error = provider
    elif provider.name != "fake" and _calls_today(db, org_id, provider.name) >= (
        get_settings().ai_daily_call_cap
    ):
        error = "daily AI call cap reached"
    else:
        try:
            run = provider.analyze(prompt.SYSTEM, user)
            output = run.output
        except (AIUnavailable, AIInvalidOutput) as exc:
            error = str(exc)[:200]
            log.warning("ai_analysis_failed lead=%s error=%s", lead.id, error)

    org_currency = org.currency or "USD"
    grounded = (
        ground(output, guard.text, form, catalog, org_currency)
        if output
        else _basic(form, org_currency)
    )
    status = "done" if output else ("failed" if has_text else "skipped")
    analysis = LeadAnalysis(
        organization_id=org_id,
        lead_id=lead.id,
        inquiry_id=inquiry.id if inquiry else None,
        provider=run.provider if run else provider_name,
        model=run.model if run else None,
        prompt_version=prompt.PROMPT_VERSION,
        schema_version=prompt.SCHEMA_VERSION,
        input_hash=input_hash,
        extracted={
            "raw": output.extraction.model_dump(mode="json") if output else {},
            "grounded": grounded.as_dict(),
        },
        assessment=output.assessment.model_dump(mode="json") if output else {},
        guard={
            "flags": guard.flags,
            "truncated": guard.truncated,
            "invisible_removed": guard.invisible_removed,
        },
        summary=(output.assessment.summary or None) if output else None,
        recommended_next_action=(output.assessment.recommended_next_action or None)
        if output
        else None,
        status=status,
        error=error,
        latency_ms=run.latency_ms if run else None,
        input_tokens=run.input_tokens if run else None,
        output_tokens=run.output_tokens if run else None,
    )
    db.add(analysis)
    db.flush()

    b = grounded.budget
    inp = ScoreInput(
        services=grounded.services,
        budget_min_minor=b.min_minor if b else None,
        budget_max_minor=b.max_minor if b else None,
        budget_comparable=bool(b and b.comparable_currency == _comparable(org_currency)),
        budget_evidence=grounded.budget_evidence,
        intent=output.assessment.intent if output else "unknown",
        urgency=grounded.urgency,
        urgency_evidence=grounded.timeline_evidence,
        buying_signals=grounded.buying_signals,
        has_name=bool(lead.full_name and lead.full_name.strip()),
        has_valid_email=bool(lead.email and "@" in lead.email),
        has_phone=bool(lead.phone_raw),
        has_company=bool(lead.company or grounded.company),
        meaningful_message=len(guard.text.split()) >= 8,
        has_timeline=grounded.timeline_source is not None,
        inquiry_count=inquiry_count,
        email=lead.email,
        industry=grounded.industry,
        injection_flags=guard.flags,
        provisional=output is None,
    )
    res = score(inp, catalog, cfg.weights, cfg.thresholds, cfg.ideal_customer)
    needs_review = res.needs_review or guard.needs_review
    db.add(
        LeadScore(
            organization_id=org_id,
            lead_id=lead.id,
            analysis_id=analysis.id,
            total=res.total,
            band=res.band,
            breakdown=[dict(f.__dict__) for f in res.factors],
            explanation=res.explanation,
            caps=res.caps,
            config_version=cfg.version,
            provisional=res.provisional,
            needs_review=needs_review,
        )
    )
    lead.score, lead.priority = res.total, res.band
    lead.score_source = analysis.provider if output else "rules"
    lead.score_provisional = res.provisional
    lead.needs_review = needs_review
    lead.ai_status = status
    record(
        db,
        org_id,
        lead.id,
        "scored",
        "ai" if output else "system",
        score=res.total,
        band=res.band,
        source=lead.score_source,
        provisional=res.provisional,
    )
    _advance_stage(db, org_id, lead)
    db.commit()
    return result_dict(db, lead)


def _comparable(currency: str) -> str:
    return "USD" if currency in {"USD", "USDT", "USDC"} else currency


def _basic(form: dict, org_currency: str) -> Grounded:
    """No usable model output: only trusted form choices count."""
    return ground(AnalysisOutput(), "", form, [], org_currency)


def _advance_stage(db: Session, org_id: uuid.UUID, lead: Lead) -> None:
    """A brand-new lead moves from "New" to "AI processed" once it is scored."""
    stages = {
        s.key: s
        for s in db.scalars(
            select(PipelineStage).where(
                PipelineStage.organization_id == org_id,
                PipelineStage.key.in_(("new", "ai_processed")),
            )
        )
    }
    new, processed = stages.get("new"), stages.get("ai_processed")
    if new and processed and lead.stage_id == new.id:
        lead.stage_id = processed.id
        record(
            db,
            org_id,
            lead.id,
            "stage_changed",
            "system",
            from_stage="new",
            to_stage="ai_processed",
            to_label=processed.label,
        )


def latest(db: Session, lead_id: uuid.UUID) -> tuple[LeadAnalysis | None, LeadScore | None]:
    a = db.scalar(
        select(LeadAnalysis)
        .where(LeadAnalysis.lead_id == lead_id)
        .order_by(LeadAnalysis.created_at.desc())
        .limit(1)
    )
    s = db.scalar(
        select(LeadScore)
        .where(LeadScore.lead_id == lead_id)
        .order_by(LeadScore.created_at.desc())
        .limit(1)
    )
    return a, s


def result_dict(db: Session, lead: Lead) -> dict:
    a, s = latest(db, lead.id)
    return {
        "lead_id": str(lead.id),
        "ai_status": lead.ai_status,
        "score": lead.score,
        "band": lead.priority,
        "score_source": lead.score_source,
        "provisional": lead.score_provisional,
        "needs_review": lead.needs_review,
        "summary": a.summary if a else None,
        "explanation": s.explanation if s else None,
    }
