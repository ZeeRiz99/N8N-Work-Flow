"""Follow-ups, replies, opt-outs and follow-up settings for logged-in members (P8)."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import AdminDep, DbSession, UserDep, csrf_protect
from app.models import FollowUp, Lead, Organization
from app.repositories.tenant import get_owned
from app.services import followups as fu_service
from app.services.activity import record

router = APIRouter(tags=["follow-ups"], dependencies=[Depends(csrf_protect)])


def _out(f: FollowUp, lead: Lead | None) -> dict:
    return {
        "id": str(f.id),
        "lead_id": str(f.lead_id),
        "lead_name": lead.full_name if lead else None,
        "lead_company": lead.company if lead else None,
        "lead_priority": lead.priority if lead else None,
        "due_at": f.due_at.isoformat(),
        "status": f.status,
        "attempt_no": f.attempt_no,
        "skip_reason": f.skip_reason,
        "draft_id": str(f.draft_id) if f.draft_id else None,
        "completed_at": f.completed_at.isoformat() if f.completed_at else None,
    }


@router.get("/follow-ups")
def list_follow_ups(
    user: UserDep,
    db: DbSession,
    status: Literal[
        "scheduled", "awaiting_approval", "done", "skipped", "cancelled", "all"
    ] = "scheduled",
    lead_id: uuid.UUID | None = None,
) -> list[dict]:
    stmt = (
        select(FollowUp, Lead)
        .join(Lead, Lead.id == FollowUp.lead_id)
        .where(FollowUp.organization_id == user.organization_id)
        .order_by(
            FollowUp.due_at.asc()
            if status in ("scheduled", "awaiting_approval")
            else FollowUp.due_at.desc()
        )
        .limit(300)
    )
    if status != "all":
        stmt = stmt.where(FollowUp.status == status)
    if lead_id:
        stmt = stmt.where(FollowUp.lead_id == lead_id)
    return [_out(f, lead) for f, lead in db.execute(stmt).all()]


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_at: datetime


@router.post("/leads/{lead_id}/follow-ups", status_code=201)
def schedule_follow_up(lead_id: uuid.UUID, body: ScheduleIn, user: UserDep, db: DbSession) -> dict:
    """Manual follow-up. The contact rules are checked again when it falls due."""
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    due = body.due_at if body.due_at.tzinfo else body.due_at.replace(tzinfo=UTC)
    if due < datetime.now(UTC):
        raise HTTPException(422, "Pick a time in the future.")
    checks = fu_service.contact_check(db, lead, ignore_cooldown=True)
    if not fu_service.allowed(checks):
        raise HTTPException(
            409, "This lead cannot be contacted: " + fu_service.failed_reason(checks)
        )
    f = fu_service.schedule(db, lead, due, user.user_id)
    db.commit()
    return _out(f, lead)


class SkipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=200)


@router.post("/follow-ups/{fu_id}/skip")
def skip_follow_up(fu_id: uuid.UUID, body: SkipIn, user: UserDep, db: DbSession) -> dict:
    f = get_owned(db, FollowUp, fu_id, user.organization_id)
    if f.status not in ("scheduled", "awaiting_approval"):
        raise HTTPException(409, f"This follow-up is {f.status}.")
    f.status, f.skip_reason, f.completed_at = "skipped", body.reason, datetime.now(UTC)
    lead = db.get(Lead, f.lead_id)
    lead.next_follow_up_at = None
    record(
        db,
        f.organization_id,
        f.lead_id,
        "follow_up_skipped",
        "user",
        user.user_id,
        reason=body.reason,
    )
    db.commit()
    return _out(f, lead)


@router.post("/follow-ups/{fu_id}/prepare")
def prepare_now(fu_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    """Write the follow-up draft now (outside the hourly schedule). Rules still apply."""
    f = get_owned(db, FollowUp, fu_id, user.organization_id)
    result = fu_service.prepare(db, f)
    return {**result, **_out(f, db.get(Lead, f.lead_id))}


class RepliedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=300)


@router.post("/leads/{lead_id}/replied")
def mark_replied(lead_id: uuid.UUID, body: RepliedIn, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    fu_service.mark_replied(db, lead, user.user_id, body.note)
    db.commit()
    return {"ok": True}


@router.post("/leads/{lead_id}/opt-out")
def opt_out(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    fu_service.opt_out(db, lead, user.user_id)
    db.commit()
    return {"ok": True}


@router.get("/leads/{lead_id}/contact-rules")
def contact_rules(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    checks = fu_service.contact_check(db, lead)
    return {
        "allowed": fu_service.allowed(checks),
        "checks": checks,
        "next_follow_up_at": lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else None,
    }


class FollowUpSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_attempts: int = Field(ge=1, le=6)
    cooldown_days: int = Field(ge=1, le=60)


@router.get("/settings/follow-ups")
def get_settings_fu(user: UserDep, db: DbSession) -> dict:
    org = db.get(Organization, user.organization_id)
    cfg = (org.settings or {}).get("follow_ups", {})
    return {
        "max_attempts": cfg.get("max_attempts", fu_service.MAX_ATTEMPTS),
        "cooldown_days": cfg.get("cooldown_days", fu_service.COOLDOWN_DAYS),
        "timezone": org.timezone,
        "business_hours": "Monday to Friday, 09:00 to 17:00 local time",
    }


@router.put("/settings/follow-ups")
def put_settings_fu(body: FollowUpSettingsIn, user: AdminDep, db: DbSession) -> dict:
    org = db.get(Organization, user.organization_id)
    settings = dict(org.settings or {})
    settings["follow_ups"] = body.model_dump()
    org.settings = settings
    db.commit()
    return get_settings_fu(user, db)
