"""Overview analytics (master prompt §7 analytics, P7 basic; expanded in P9). All numbers are
computed by SQL in the caller's organization."""

import statistics
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select

from app.api.deps import AdminDep, DbSession, UserDep, csrf_protect
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


# ---------------------------------------------------------------- P9: sources, funnel, team


def source_rows(db, org_id, since) -> list[dict]:
    """Per lead source: leads, high priority, won, conversion and median score."""
    from app.models import LeadSource

    won_stage = select(PipelineStage.id).where(
        PipelineStage.organization_id == org_id, PipelineStage.category == "won"
    )
    rows = db.execute(
        select(
            LeadSource.label,
            func.count(Lead.id),
            func.count(Lead.id).filter(Lead.priority == "high"),
            func.count(Lead.id).filter(Lead.stage_id.in_(won_stage)),
            func.percentile_cont(0.5).within_group(Lead.score),
        )
        .join(Lead, and_(Lead.source_id == LeadSource.id, Lead.created_at >= since), isouter=True)
        .where(LeadSource.organization_id == org_id)
        .group_by(LeadSource.id, LeadSource.label)
        .order_by(func.count(Lead.id).desc(), LeadSource.label)
    ).all()
    return [
        {
            "source": label,
            "leads": n,
            "high": h,
            "won": w,
            "conversion": round(w / n, 3) if n else 0.0,
            "median_score": round(m, 1) if m is not None else None,
        }
        for label, n, h, w, m in rows
    ]


@router.get("/sources")
def sources(user: UserDep, db: DbSession, days: int = Query(30, ge=1, le=365)) -> dict:
    since, _ = _window(days)
    return {"days": days, "rows": source_rows(db, user.organization_id, since)}


@router.get("/funnel")
def funnel(user: UserDep, db: DbSession, days: int = Query(90, ge=1, le=365)) -> dict:
    """Leads created in the window, by how far they got. A lead counts at its current stage
    and every open stage before it (a won lead passed every step)."""
    since, _ = _window(days)
    stages = db.scalars(
        select(PipelineStage)
        .where(PipelineStage.organization_id == user.organization_id)
        .order_by(PipelineStage.position)
    ).all()
    current = dict(
        db.execute(
            select(Lead.stage_id, func.count())
            .where(
                Lead.organization_id == user.organization_id,
                Lead.created_at >= since,
                Lead.archived_at.is_(None),
            )
            .group_by(Lead.stage_id)
        ).all()
    )
    total = sum(current.values())
    open_stages = [s for s in stages if s.category == "open"]
    won = [s for s in stages if s.category == "won"]
    lost = sum(current.get(s.id, 0) for s in stages if s.category == "lost")
    won_n = sum(current.get(s.id, 0) for s in won)
    steps = []
    for i, s in enumerate(open_stages):
        reached = sum(current.get(x.id, 0) for x in open_stages[i:]) + won_n
        steps.append({"key": s.key, "label": s.label, "reached": reached})
    steps.append({"key": "won", "label": won[0].label if won else "Won", "reached": won_n})
    for i, st in enumerate(steps):
        prev = steps[i - 1]["reached"] if i else total
        st["from_previous"] = round(st["reached"] / prev, 3) if prev else 0.0
    return {
        "days": days,
        "total": total,
        "steps": steps,
        "lost": lost,
        "win_rate": round(won_n / total, 3) if total else 0.0,
    }


@router.get("/team")
def team(user: UserDep, db: DbSession, days: int = Query(30, ge=1, le=365)) -> dict:
    """Per member: leads assigned, drafts approved, emails sent, leads won."""
    from app.models import OrganizationMember, User

    since, _ = _window(days)
    org_id = user.organization_id
    members = db.execute(
        select(User.id, User.full_name, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == org_id)
        .order_by(User.full_name)
    ).all()
    won_stage = select(PipelineStage.id).where(
        PipelineStage.organization_id == org_id, PipelineStage.category == "won"
    )
    out = []
    for uid, name, role in members:
        assigned = _count(
            db, Lead.organization_id == org_id, Lead.assigned_to == uid, Lead.archived_at.is_(None)
        )
        won = _count(
            db,
            Lead.organization_id == org_id,
            Lead.assigned_to == uid,
            Lead.stage_id.in_(won_stage),
        )
        approved = (
            db.scalar(
                select(func.count())
                .select_from(CommunicationDraft)
                .where(
                    CommunicationDraft.organization_id == org_id,
                    CommunicationDraft.approved_by == uid,
                    CommunicationDraft.approved_at >= since,
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
                    CommunicationDraft.approved_by == uid,
                    CommunicationDraft.status == "sent",
                    CommunicationDraft.sent_at >= since,
                )
            )
            or 0
        )
        out.append(
            {
                "user_id": str(uid),
                "name": name,
                "role": role,
                "assigned": assigned,
                "approved": approved,
                "sent": sent,
                "won": won,
            }
        )
    return {"days": days, "rows": out}


@router.get("/export")
def export(user: UserDep, db: DbSession, days: int = Query(30, ge=1, le=365)):
    """Source performance and the daily series as CSV (numbers only, formula-safe)."""
    import csv
    import io

    from fastapi.responses import Response

    since, _ = _window(days)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "label", "leads", "high", "won", "conversion", "median_score"])
    for r in source_rows(db, user.organization_id, since):
        w.writerow(
            [
                "source",
                "'" + r["source"] if r["source"][:1] in "=+-@" else r["source"],
                r["leads"],
                r["high"],
                r["won"],
                r["conversion"],
                r["median_score"],
            ]
        )
    for p in trends(user, db, max(days, 7))["series"]:
        w.writerow(["day", p["date"], p["leads"], p["high"], "", "", ""])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="replyline-analytics-{days}d.csv"'},
    )


# ---------------------------------------------------------------- report snapshots


@router.get("/reports")
def list_reports(user: UserDep, db: DbSession) -> list[dict]:
    from app.models import ReportSnapshot
    from app.services.reports import snapshot_out

    rows = db.scalars(
        select(ReportSnapshot)
        .where(ReportSnapshot.organization_id == user.organization_id)
        .order_by(ReportSnapshot.period_start.desc())
        .limit(60)
    ).all()
    return [snapshot_out(s) for s in rows]


@router.post("/reports/{kind}")
def generate_report(kind: str, user: AdminDep, db: DbSession) -> dict:
    """Create today's report now (outside the schedule). One per period: repeats return it."""
    from fastapi import HTTPException

    from app.services import reports

    org = db.get(Organization, user.organization_id)
    if kind == "daily":
        snap = reports.make_daily(db, org)
    elif kind == "source_performance":
        snap = reports.make_source_performance(db, org)
    else:
        raise HTTPException(404, "Unknown report.")
    return reports.snapshot_out(snap)
