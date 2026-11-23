"""AI analysis and scoring settings for logged-in members (master prompt §8, §10)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update

from app.api.deps import AdminDep, DbSession, UserDep, csrf_protect
from app.models import Lead, ScoringConfig
from app.repositories.tenant import get_owned
from app.scoring.engine import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    LABELS,
    ConfigError,
    validate_config,
)
from app.services import analysis
from app.services.activity import record

router = APIRouter(tags=["ai"], dependencies=[Depends(csrf_protect)])


@router.get("/leads/{lead_id}/analysis")
def get_analysis(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    """The latest analysis and score, with every fact's quote and every factor's reason."""
    get_owned(db, Lead, lead_id, user.organization_id)
    a, s = analysis.latest(db, lead_id)
    out: dict = {"analysis": None, "score": None}
    if a is not None:
        assess = a.assessment or {}
        out["analysis"] = {
            "id": str(a.id),
            "status": a.status,
            "error": a.error,
            "provider": a.provider,
            "model": a.model,
            "prompt_version": a.prompt_version,
            "latency_ms": a.latency_ms,
            "created_at": a.created_at.isoformat(),
            "facts": (a.extracted or {}).get("grounded", {}),
            "intent": assess.get("intent"),
            "red_flags": assess.get("red_flags", []),
            "summary": a.summary,
            "recommended_next_action": a.recommended_next_action,
            "guard_flags": (a.guard or {}).get("flags", []),
        }
    if s is not None:
        out["score"] = {
            "total": s.total,
            "band": s.band,
            "factors": [{**f, "label": LABELS.get(f["key"], f["key"])} for f in s.breakdown],
            "explanation": s.explanation,
            "caps": s.caps,
            "provisional": s.provisional,
            "needs_review": s.needs_review,
            "config_version": s.config_version,
            "created_at": s.created_at.isoformat(),
        }
    return out


@router.post("/leads/{lead_id}/reanalyze")
def reanalyze(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    """Run the analysis again now (an unchanged message is served from the cache)."""
    get_owned(db, Lead, lead_id, user.organization_id)
    record(db, user.organization_id, lead_id, "reanalysis_requested", "user", user.user_id)
    return analysis.analyze_lead(db, user.organization_id, lead_id, force=True)


# ---------------------------------------------------------------- scoring settings


class ScoringIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: dict[str, int]
    thresholds: dict[str, int]
    ideal_industries: list[str] = Field(default_factory=list, max_length=20)


def _config_out(cfg: ScoringConfig) -> dict:
    return {
        "version": cfg.version,
        "weights": cfg.weights,
        "thresholds": cfg.thresholds,
        "ideal_industries": (cfg.ideal_customer or {}).get("industries", []),
        "labels": LABELS,
        "defaults": {"weights": DEFAULT_WEIGHTS, "thresholds": DEFAULT_THRESHOLDS},
        "updated_at": cfg.created_at.isoformat(),
    }


@router.get("/settings/scoring")
def get_scoring(user: UserDep, db: DbSession) -> dict:
    cfg = analysis.active_config(db, user.organization_id)
    db.commit()
    return _config_out(cfg)


@router.put("/settings/scoring")
def put_scoring(body: ScoringIn, user: AdminDep, db: DbSession) -> dict:
    """Saves a new version. Existing scores keep the version that produced them; new and
    re-analyzed leads use the new one."""
    try:
        validate_config(body.weights, body.thresholds)
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    current = analysis.active_config(db, user.organization_id)
    industries = sorted({i.strip()[:60] for i in body.ideal_industries if i.strip()})
    db.execute(
        update(ScoringConfig)
        .where(ScoringConfig.organization_id == user.organization_id)
        .values(is_active=False)
    )
    db.flush()
    cfg = ScoringConfig(
        organization_id=user.organization_id,
        version=current.version + 1,
        weights=body.weights,
        thresholds={k: body.thresholds[k] for k in ("high_min", "medium_min")},
        ideal_customer={"industries": industries} if industries else {},
        is_active=True,
        created_by=user.user_id,
    )
    db.add(cfg)
    db.commit()
    return _config_out(cfg)


@router.post("/settings/scoring/rescore")
def rescore(user: AdminDep, db: DbSession) -> dict:
    """Recompute all open leads with the active config, from stored analyses (no AI call)."""
    changed = analysis.rescore_org(db, user.organization_id, user.user_id)
    return {"changed": changed, "version": analysis.active_config(db, user.organization_id).version}
