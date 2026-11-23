"""Overview analytics (master prompt §7 analytics, P7 basic; expanded in P9). All numbers are
computed by SQL in the caller's organization."""

import statistics
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select

from app.api.deps import DbSession, UserDep, csrf_protect
from app.models import (
    CommunicationDraft,
    CommunicationLog,
    FollowUp,
    Lead,
    LeadActivity,
    Organization,
    PipelineStage,
    WorkflowExecution,
)

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(csrf_protect)])


def _window(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - timedelta(days=days), now


def _count(db, *where) -> int:
    return db.scalar(select(func.count()).select_from(Lead).where(*where)) or 0


def median_first_reply_minutes(db, org_id, since) -> tuple[float | None, int]:
    """Minutes from a lead's first inquiry to its first sent email, for leads first answered
    in the window. Median, because one slow weekend reply would distort a mean."""
    first_sent = (
        select(CommunicationLog.lead_id, func.min(CommunicationLog.occurred_at).label("at"))
        .where(
            CommunicationLog.organization_id == org_id,
            CommunicationLog.direction == "out",
            CommunicationLog.status == "sent",
        )
        .group_by(CommunicationLog.lead_id)
        .subquery()
    )
    rows = db.execute(
        select(Lead.first_inquiry_at, first_sent.c.at)
        .join(first_sent, first_sent.c.lead_id == Lead.id)
        .where(Lead.organization_id == org_id, first_sent.c.at >= since)
    ).all()
    minutes = [max(0.0, (sent - first).total_seconds() / 60) for first, sent in rows]
    return (round(statistics.median(minutes), 1) if minutes else None), len(minutes)


def _next_step(lead: Lead, pending: set, follow: dict) -> str:
    if lead.ai_status in ("pending", "processing"):
        return "AI processing"
    if lead.id in pending:
        return "Approve the reply draft"
    if lead.ai_status == "failed":
        return "Check the provisional score"
    if lead.id in follow:
        return f"Follow up {follow[lead.id].strftime('%b %d')}"
    if lead.priority == "high":
        return "Reply today"
    return "Review"


@router.get("/overview")
def overview(user: UserDep, db: DbSession, days: int = Query(7, ge=1, le=365)) -> dict:
    org_id = user.organization_id
    org = db.get(Organization, org_id)
    since, now = _window(days)
    prev = since - timedelta(days=days)
    in_org = Lead.organization_id == org_id
    live = Lead.archived_at.is_(None)
    new_now = _count(db, in_org, Lead.created_at >= since)
    new_prev = _count(db, in_org, Lead.created_at >= prev, Lead.created_at < since)
    high = _count(db, in_org, live, Lead.created_at >= since, Lead.priority == "high")
    waiting = (
        db.scalar(
            select(func.count())
            .select_from(CommunicationDraft)
            .where(
                CommunicationDraft.organization_id == org_id,
                CommunicationDraft.status == "pending_approval",
            )
        )
        or 0
    )
    median, answered = median_first_reply_minutes(db, org_id, since)
    mix = dict(
        db.execute(
            select(Lead.priority, func.count())
            .where(in_org, live, Lead.created_at >= since)
            .group_by(Lead.priority)
        ).all()
    )
    stages = db.execute(
        select(PipelineStage.label, PipelineStage.category, func.count(Lead.id))
        .join(
            Lead, and_(Lead.stage_id == PipelineStage.id, Lead.archived_at.is_(None)), isouter=True
        )
        .where(PipelineStage.organization_id == org_id)
        .group_by(
            PipelineStage.id, PipelineStage.label, PipelineStage.category, PipelineStage.position
        )
        .order_by(PipelineStage.position)
    ).all()
    week = now - timedelta(days=7)
    runs = (
        db.scalar(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == org_id, WorkflowExecution.created_at >= week
            )
        )
        or 0
    )
    sent = (
        db.scalar(
            select(func.count())
            .select_from(CommunicationDraft)
            .where(
                CommunicationDraft.organization_id == org_id,
                CommunicationDraft.status == "sent",
                CommunicationDraft.sent_at >= week,
            )
        )
        or 0
    )
    alerts = (
        db.scalar(
            select(func.count())
            .select_from(LeadActivity)
            .where(
                LeadActivity.organization_id == org_id,
                LeadActivity.type == "alert_sent",
                LeadActivity.created_at >= week,
            )
        )
        or 0
    )
    latest = db.scalars(
        select(Lead).where(in_org, live).order_by(Lead.last_interaction_at.desc()).limit(6)
    ).all()
    ids = [x.id for x in latest]
    pending = set(
        db.scalars(
            select(CommunicationDraft.lead_id).where(
                CommunicationDraft.lead_id.in_(ids), CommunicationDraft.status == "pending_approval"
            )
        )
    )
    follow = dict(
        db.execute(
            select(FollowUp.lead_id, func.min(FollowUp.due_at))
            .where(FollowUp.lead_id.in_(ids), FollowUp.status == "scheduled")
            .group_by(FollowUp.lead_id)
        ).all()
    )
    total_mix = sum(mix.values()) or 1
    return {
        "days": days,
        "cards": {
            "new_leads": new_now,
            "new_leads_previous": new_prev,
            "high_priority": high,
            "awaiting_approval": waiting,
            "median_first_reply_minutes": median,
            "answered_leads": answered,
            "reply_target_minutes": (org.settings or {}).get("reply_target_minutes", 120),
        },
        "priority_mix": [
            {"priority": p, "count": mix.get(p, 0), "share": round(mix.get(p, 0) / total_mix, 3)}
            for p in ("high", "medium", "low", "unscored")
        ],
        "stages": [{"label": lbl, "category": cat, "count": n} for lbl, cat, n in stages],
        "automation_week": {"runs": runs, "emails_sent": sent, "alerts": alerts},
        "latest": [
            {
                "id": str(x.id),
                "full_name": x.full_name,
                "company": x.company,
                "priority": x.priority,
                "score": x.score,
                "ai_status": x.ai_status,
                "next_step": _next_step(x, pending, follow),
                "last_interaction_at": x.last_interaction_at.isoformat(),
            }
            for x in latest
        ],
    }


@router.get("/trends")
def trends(user: UserDep, db: DbSession, days: int = Query(30, ge=7, le=365)) -> dict:
    """New leads per day (and how many were High), every day present even when zero."""
    since, now = _window(days)
    tz = "UTC"
    day = func.date_trunc("day", func.timezone(tz, Lead.created_at)).label("day")
    rows = db.execute(
        select(day, func.count(), func.count().filter(Lead.priority == "high"))
        .where(Lead.organization_id == user.organization_id, Lead.created_at >= since)
        .group_by(day)
    ).all()
    by_day = {d.date(): (n, h) for d, n, h in rows}
    start = since.date()
    series = []
    for i in range(days + 1):
        d = start + timedelta(days=i)
        if d > now.date():
            break
        n, h = by_day.get(d, (0, 0))
        series.append({"date": d.isoformat(), "leads": n, "high": h})
    return {"days": days, "series": series}
