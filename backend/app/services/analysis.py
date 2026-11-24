"""Analyze a lead (master prompt §8): guard -> cache -> provider -> ground -> score -> persist.

- The AI only extracts and judges; the score is computed by code from grounded facts.
- An unchanged inquiry (same input hash) reuses the stored model output, so it is never
  re-sent to the provider.
- If the provider fails (outage, circuit open, daily cap, bad output) the lead still gets a
  provisional score from trusted form choices and contact details, and ai_status "failed" so
  it can be re-run.
- Idempotent: analyzing a lead that is already done returns the stored result unless forced.
"""

import logging
import uuid
from datetime import UTC, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.fake_provider import FakeAIProvider
from app.ai.pipeline import LeadFacts, assess, prepare
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
from app.scoring.engine import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from app.services.activity import record

log = logging.getLogger(__name__)
CACHE_HIT = "cache hit"


def get_provider() -> AIProvider:
    s = get_settings()
    if s.ai_provider == "fake":
        return FakeAIProvider()
    from app.ai.gemini_provider import GeminiProvider  # the only SDK import site (D11)

    model, fallback = s.gemini_models
    return GeminiProvider(
        s.gemini_api_key,
        model,
        fallback,
        s.ai_timeout_seconds,
        daily_budget=s.gemini_daily_budget,
    )


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


def _org_cap(org: Organization) -> int:
    """The organization's own daily limit (AI settings), never above the server limit."""
    server = get_settings().ai_daily_call_cap
    return min(int((org.settings or {}).get("ai", {}).get("daily_cap", server)), server)


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
    db: Session,
    org_id: uuid.UUID,
    lead_id: uuid.UUID,
    force: bool = False,
    provider: AIProvider | None = None,
) -> dict | None:
    """provider: override the configured provider (sample data uses the offline one)."""
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

    form = (inquiry.form_fields if inquiry else {}) or {}
    prep = prepare(inquiry.message if inquiry else "", form, catalog, org.name)
    guard, user, input_hash = prep.guard, prep.user_prompt, prep.input_hash
    has_text = prep.has_text

    output: AnalysisOutput | None = None
    run: AIResult | None = None
    error: str | None = None
    provider = provider or _provider_or_error()
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
    elif provider.name != "fake" and _calls_today(db, org_id, provider.name) >= _org_cap(org):
        error = "daily AI call cap reached"
    else:
        try:
            run = provider.analyze(prompt.SYSTEM, user)
            output = run.output
        except (AIUnavailable, AIInvalidOutput) as exc:
            error = str(exc)[:200]
            log.warning("ai_analysis_failed lead=%s error=%s", lead.id, error)

    org_currency = org.currency or "USD"
    lead_facts = LeadFacts(lead.full_name, lead.email, lead.phone_raw, lead.company, inquiry_count)
    done = assess(
        output,
        prep,
        form,
        catalog,
        org_currency,
        lead_facts,
        cfg.weights,
        cfg.thresholds,
        cfg.ideal_customer,
    )
    grounded, res, needs_review = done.grounded, done.result, done.needs_review
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

    _save_score(db, org_id, lead, analysis.id, res, needs_review, cfg.version)
    lead.score_source = analysis.provider if output else "rules"
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


# ---------------------------------------------------------------- re-score (no AI call)


def rescore_org(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> int:
    """Recompute every open lead's score with the active scoring config from its latest stored
    analysis. No AI call is made; a lead whose last analysis failed stays provisional."""
    org = db.get(Organization, org_id)
    catalog = _catalog(db, org_id)
    cfg = active_config(db, org_id)
    leads = db.scalars(
        select(Lead).where(Lead.organization_id == org_id, Lead.archived_at.is_(None))
    ).all()
    changed = 0
    for lead in leads:
        a, _ = latest(db, lead.id)
        if a is None or a.status == "skipped":
            continue
        inquiry = db.scalar(
            select(LeadInquiry)
            .where(LeadInquiry.lead_id == lead.id)
            .order_by(LeadInquiry.received_at.desc())
            .limit(1)
        )
        count = db.scalar(
            select(func.count()).select_from(LeadInquiry).where(LeadInquiry.lead_id == lead.id)
        )
        form = (inquiry.form_fields if inquiry else {}) or {}
        prep = prepare(inquiry.message if inquiry else "", form, catalog, org.name)
        output = (
            AnalysisOutput.model_validate(
                {"extraction": a.extracted.get("raw", {}), "assessment": a.assessment}
            )
            if a.status == "done"
            else None
        )
        facts = LeadFacts(lead.full_name, lead.email, lead.phone_raw, lead.company, count or 1)
        done = assess(
            output,
            prep,
            form,
            catalog,
            org.currency or "USD",
            facts,
            cfg.weights,
            cfg.thresholds,
            cfg.ideal_customer,
        )
        res = done.result
        before = (lead.score, lead.priority)
        _save_score(db, org_id, lead, a.id, res, done.needs_review, cfg.version)
        if before != (res.total, res.band):
            changed += 1
            record(
                db,
                org_id,
                lead.id,
                "rescored",
                "user" if actor_id else "system",
                actor_id,
                from_score=before[0],
                score=res.total,
                band=res.band,
                config_version=cfg.version,
            )
    db.commit()
    return changed


def _save_score(db, org_id, lead, analysis_id, res, needs_review: bool, config_version: int):
    db.add(
        LeadScore(
            organization_id=org_id,
            lead_id=lead.id,
            analysis_id=analysis_id,
            total=res.total,
            band=res.band,
            breakdown=[dict(f.__dict__) for f in res.factors],
            explanation=res.explanation,
            caps=res.caps,
            config_version=config_version,
            provisional=res.provisional,
            needs_review=needs_review,
        )
    )
    lead.score, lead.priority = res.total, res.band
    lead.score_provisional = res.provisional
    lead.needs_review = needs_review


# ---------------------------------------------------------------- automatic retry


RETRY_BASE_MINUTES = 5
RETRY_MAX_DELAY_MINUTES = 360
RETRY_MAX_ATTEMPTS = 8  # about 16 hours of backoff: covers a free-tier daily quota reset


def retry_delay_minutes(failures: int) -> int:
    return min(RETRY_BASE_MINUTES * 2 ** max(failures - 1, 0), RETRY_MAX_DELAY_MINUTES)


def due_for_retry(db: Session, now: datetime | None = None, limit: int = 50) -> list[Lead]:
    """Failed leads whose backoff has passed. Free-tier limits are handled by queueing (§8.7):
    a failed lead is never dropped, it is retried with growing gaps, then left for a human."""
    now = now or datetime.now(UTC)
    due = []
    leads = db.scalars(
        select(Lead)
        .where(Lead.ai_status == "failed", Lead.archived_at.is_(None))
        .order_by(Lead.last_interaction_at.desc())
        .limit(limit)
    ).all()
    for lead in leads:
        runs = db.scalars(
            select(LeadAnalysis)
            .where(LeadAnalysis.lead_id == lead.id)
            .order_by(LeadAnalysis.created_at.desc())
            .limit(RETRY_MAX_ATTEMPTS + 1)
        ).all()
        failures = 0
        for r in runs:
            if r.status != "failed":
                break
            failures += 1
        if not runs or failures >= RETRY_MAX_ATTEMPTS:
            continue
        wait = retry_delay_minutes(failures)
        if (now - runs[0].created_at).total_seconds() >= wait * 60:
            due.append(lead)
    return due


def retry_failed(db: Session, now: datetime | None = None) -> int:
    """Retry due leads; stop at the first one that fails again (the provider is still down,
    so hammering it would only burn quota). Returns how many succeeded."""
    ok = 0
    for lead in due_for_retry(db, now):
        out = analyze_lead(db, lead.organization_id, lead.id, force=True)
        if not out or out["ai_status"] != "done":
            break
        ok += 1
    return ok


STUCK_AFTER_SECONDS = 45
# A lead in "processing" may legitimately wait on the AI for minutes: 2 models x 3 attempts x a
# 30 s timeout plus backoff (about 4 min). Requeueing it earlier ran a second analysis in
# parallel and spent the daily budget twice.
PROCESSING_STUCK_AFTER_SECONDS = 300
MAX_INTAKE_EVENTS = 3


def requeue_stuck_leads(db: Session, now: datetime | None = None) -> int:
    """Leads still pending/processing well after their event was delivered: n8n called back
    while the backend was down (or a run died). Re-send the intake event through the outbox
    (a new event id, so the idempotency keys allow it), at most 3 events per lead (§12.5 #16:
    killing the backend mid-flow loses nothing)."""
    from datetime import timedelta

    from app.models import OutboxEvent
    from app.services.leads import _event_envelope

    now = now or datetime.now(UTC)
    from sqlalchemy import and_, or_

    cutoff = now - timedelta(seconds=STUCK_AFTER_SECONDS)
    processing_cutoff = now - timedelta(seconds=PROCESSING_STUCK_AFTER_SECONDS)
    leads = db.scalars(
        select(Lead)
        .where(
            or_(
                and_(Lead.ai_status == "pending", Lead.updated_at < cutoff),
                and_(Lead.ai_status == "processing", Lead.updated_at < processing_cutoff),
            ),
            Lead.archived_at.is_(None),
        )
        .limit(50)
    ).all()
    requeued = 0
    for lead in leads:
        events = db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "lead.created",
                OutboxEvent.payload["data"]["lead_id"].astext == str(lead.id),
            )
        ).all()
        if not events or len(events) >= MAX_INTAKE_EVENTS:
            continue  # never emitted (manual lead without message) or out of attempts
        if any(e.status != "delivered" or e.created_at > cutoff for e in events):
            continue  # a delivery is still on its way
        data = dict(events[-1].payload.get("data", {}))
        data["requeued"] = True
        db.add(
            OutboxEvent(
                organization_id=lead.organization_id,
                event_type="lead.created",
                payload=_event_envelope("lead.created", lead.organization_id, data),
            )
        )
        record(
            db, lead.organization_id, lead.id, "intake_requeued", "system", attempt=len(events) + 1
        )
        requeued += 1
    db.commit()
    return requeued


class AIRetryWorker:
    """Background thread: every few minutes, retries failed analyses that are due."""

    def __init__(self, session_factory, poll_seconds: float = 60.0) -> None:
        import threading

        self._factory, self._poll = session_factory, poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ai-retry", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        first = True
        # Run once right away (a restart after a crash is exactly when leads are stuck),
        # then every poll interval.
        while first or not self._stop.wait(self._poll):
            first = False
            try:
                with self._factory() as db:
                    stuck = requeue_stuck_leads(db)
                    n = retry_failed(db)
                    if n or stuck:
                        log.info("ai_retry recovered=%s requeued_stuck=%s", n, stuck)
            except Exception:  # noqa: BLE001 - never let the worker die
                log.exception("ai retry loop error")


def preview_scores(
    db: Session, org_id: uuid.UUID, weights: dict, thresholds: dict, limit: int = 20
) -> list[dict]:
    """How recent leads would score with proposed settings, from their stored analyses.
    Nothing is saved and no AI call is made."""
    from app.scoring.engine import validate_config

    validate_config(weights, thresholds)
    org = db.get(Organization, org_id)
    catalog = _catalog(db, org_id)
    cfg = active_config(db, org_id)
    leads = db.scalars(
        select(Lead)
        .where(Lead.organization_id == org_id, Lead.archived_at.is_(None), Lead.score.is_not(None))
        .order_by(Lead.last_interaction_at.desc())
        .limit(limit)
    ).all()
    out = []
    for lead in leads:
        a, _ = latest(db, lead.id)
        if a is None or a.status == "skipped":
            continue
        inquiry = db.scalar(
            select(LeadInquiry)
            .where(LeadInquiry.lead_id == lead.id)
            .order_by(LeadInquiry.received_at.desc())
            .limit(1)
        )
        form = (inquiry.form_fields if inquiry else {}) or {}
        prep = prepare(inquiry.message if inquiry else "", form, catalog, org.name)
        output = (
            AnalysisOutput.model_validate(
                {"extraction": a.extracted.get("raw", {}), "assessment": a.assessment}
            )
            if a.status == "done"
            else None
        )
        facts = LeadFacts(lead.full_name, lead.email, lead.phone_raw, lead.company, 1)
        res = assess(
            output,
            prep,
            form,
            catalog,
            org.currency or "USD",
            facts,
            weights,
            thresholds,
            cfg.ideal_customer,
        ).result
        out.append(
            {
                "lead_id": str(lead.id),
                "name": lead.full_name,
                "old_score": lead.score,
                "old_band": lead.priority,
                "new_score": res.total,
                "new_band": res.band,
            }
        )
    return out
