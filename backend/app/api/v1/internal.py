"""Internal API for n8n only. Service key required; blocked at the reverse proxy in production.

The backend decides; n8n only sequences and delivers (D10).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession, ServiceOrg
from app.core.config import get_settings
from app.models import Lead, LeadInquiry, ReportSnapshot, WorkflowExecution
from app.services.analysis import analyze_lead
from app.services.idempotency import claim_once
from app.services.outbox import redispatch_failed

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health")
def internal_health(org: ServiceOrg) -> dict:
    return {"status": "ok", "organization": org.slug}


@router.post("/leads/{lead_id}/analyze")
def analyze(
    lead_id: uuid.UUID,
    org: ServiceOrg,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Analyze once per event. A redelivered event gets the stored result and
    first_delivery=false, so W1 does not alert or draft a second time."""
    result = analyze_lead(db, org.id, lead_id)
    if result is None:
        raise HTTPException(404, "Lead not found.")
    result["first_delivery"] = claim_once(db, org.id, "n8n:analyze", idempotency_key, result)
    return result


@router.get("/leads/{lead_id}/alert-summary")
def alert_summary(lead_id: uuid.UUID, org: ServiceOrg, db: DbSession) -> dict:
    """Facts only, plain text, with the dashboard link in the text (not a button; ADR 005)."""
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if lead is None:
        raise HTTPException(404, "Lead not found.")
    inquiry = db.scalar(
        select(LeadInquiry)
        .where(LeadInquiry.lead_id == lead.id, LeadInquiry.organization_id == org.id)
        .order_by(LeadInquiry.received_at.desc())
        .limit(1)
    )
    excerpt = " ".join((inquiry.message if inquiry else "").split())[:280]
    link = f"{get_settings().frontend_public_url.rstrip('/')}/leads"
    score = "not scored" if lead.score is None else f"{lead.score}/100"
    title = f"New {lead.priority} priority lead: {lead.full_name}"
    lines = [
        title,
        f"Company: {lead.company or 'not given'}",
        f"Score: {score} ({lead.score_source or 'n/a'})",
        f"Message: {excerpt}",
        f"Open in Replyline: {link}",
    ]
    return {
        "title": title,
        "text": "\n".join(lines),
        "link": link,
        "priority": lead.priority,
        "score": lead.score,
    }


class WorkflowRunIn(BaseModel):
    workflow_key: str = Field(max_length=40)
    n8n_execution_id: str = Field(max_length=40)
    status: Literal["running", "success", "failed", "retrying", "skipped"]
    lead_id: uuid.UUID | None = None
    request_id: str | None = Field(default=None, max_length=64)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = Field(default=None, max_length=2000)
    meta: dict = Field(default_factory=dict)


@router.post("/workflow-runs")
def log_workflow_run(run: WorkflowRunIn, org: ServiceOrg, db: DbSession) -> dict:
    """Upsert by (workflow_key, n8n_execution_id): a retried log call never makes a second row."""
    if run.lead_id is not None:
        owned = db.scalar(
            select(Lead.id).where(Lead.id == run.lead_id, Lead.organization_id == org.id)
        )
        if owned is None:
            raise HTTPException(404, "Lead not found.")
    values = run.model_dump()
    values["organization_id"] = org.id
    stmt = insert(WorkflowExecution).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["workflow_key", "n8n_execution_id"],
        set_={k: stmt.excluded[k] for k in ("status", "finished_at", "error_message", "meta")},
    ).returning(WorkflowExecution.id)
    row_id = db.scalar(stmt)
    db.commit()
    return {"id": str(row_id), "status": run.status}


@router.post("/outbox/redispatch")
def outbox_redispatch(request: Request, org: ServiceOrg, db: DbSession) -> dict:
    """W9b sweeper: requeue failed events and deliver stalled ones right away (also covers a
    dead dispatcher thread)."""
    count = redispatch_failed(db)
    import httpx

    from app.services.outbox import dispatch_once

    settings = get_settings()
    with httpx.Client(timeout=settings.outbox_http_timeout_seconds) as client:
        delivered = dispatch_once(db, settings, client)
    worker = getattr(request.app.state, "outbox", None)
    if worker is not None:
        worker.nudge()
    return {"requeued": count, "dispatched": delivered}


# ---------------------------------------------------------------- drafts (W4, W4b)


@router.post("/leads/{lead_id}/drafts/generate")
def internal_generate_draft(
    lead_id: uuid.UUID,
    org: ServiceOrg,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict:
    """W4: write a first-reply draft into the Approvals queue. A redelivered event gets
    first_delivery=false and no second draft."""
    from app.services import approvals, drafting

    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if lead is None:
        raise HTTPException(404, "Lead not found.")
    if not claim_once(db, org.id, "n8n:draft", idempotency_key, {"lead_id": str(lead_id)}):
        db.commit()
        return {"first_delivery": False, "skipped": "already handled"}
    if lead.do_not_contact or not lead.email:
        db.commit()
        return {"first_delivery": True, "skipped": "lead cannot be contacted"}
    style = (org.settings or {}).get("ai", {}).get("default_style", "professional")
    try:
        d = drafting.generate_draft(db, org.id, lead.id, style)
    except drafting.DraftRefused as exc:
        db.commit()
        return {"first_delivery": True, "skipped": str(exc)}
    row = approvals.save_generated(db, org.id, lead, d, None)
    db.commit()
    return {"first_delivery": True, "draft_id": str(row.id), "all_passed": d["all_passed"]}


class MarkSentIn(BaseModel):
    provider_message_id: str | None = Field(default=None, max_length=200)


class MarkFailedIn(BaseModel):
    error: str = Field(min_length=1, max_length=300)


@router.post("/drafts/{draft_id}/claim-send")
def claim_send(draft_id: uuid.UUID, org: ServiceOrg, db: DbSession) -> dict:
    """W4b: the only way to get a draft for sending. 409 = not approved or already claimed."""
    from app.services import approvals

    d = approvals.claim_send(db, org.id, draft_id)
    if d is None:
        raise HTTPException(409, "Draft is not approved or is already being sent.")
    return {"draft_id": str(d.id), "to": d.to_address, "subject": d.subject, "body": d.body}


@router.post("/drafts/{draft_id}/mark-sent")
def mark_sent(draft_id: uuid.UUID, body: MarkSentIn, org: ServiceOrg, db: DbSession) -> dict:
    from app.services import approvals

    try:
        d = approvals.mark_sent(db, org.id, draft_id, body.provider_message_id)
    except approvals.DraftStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"draft_id": str(d.id), "status": d.status}


@router.post("/drafts/{draft_id}/mark-failed")
def mark_failed(draft_id: uuid.UUID, body: MarkFailedIn, org: ServiceOrg, db: DbSession) -> dict:
    from app.services import approvals

    try:
        d = approvals.mark_failed(db, org.id, draft_id, body.error)
    except approvals.DraftStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"draft_id": str(d.id), "status": d.status}


# ---------------------------------------------------------------- W9 error monitor

ALERT_THROTTLE_MINUTES = 10


class WorkflowErrorIn(BaseModel):
    workflow_key: str = Field(max_length=40)
    workflow_name: str | None = Field(default=None, max_length=200)
    n8n_execution_id: str = Field(max_length=40)
    last_node: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=2000)


@router.post("/workflow-errors")
def log_workflow_error(err: WorkflowErrorIn, org: ServiceOrg, db: DbSession) -> dict:
    """Log a failed run and decide whether to alert. The backend throttles alerts to one per
    workflow per 10 minutes, so n8n keeps no state (§9.3 W9)."""
    from datetime import UTC, timedelta

    from sqlalchemy import func as sa_func

    now = datetime.now(UTC)
    recent_alert = db.scalar(
        select(sa_func.count())
        .select_from(WorkflowExecution)
        .where(
            WorkflowExecution.organization_id == org.id,
            WorkflowExecution.workflow_key == err.workflow_key,
            WorkflowExecution.status == "failed",
            WorkflowExecution.meta["alerted"].astext == "true",
            WorkflowExecution.finished_at >= now - timedelta(minutes=ALERT_THROTTLE_MINUTES),
        )
    )
    should_alert = not recent_alert
    stmt = insert(WorkflowExecution).values(
        organization_id=org.id,
        workflow_key=err.workflow_key,
        n8n_execution_id=err.n8n_execution_id,
        status="failed",
        finished_at=now,
        error_message=err.message,
        meta={
            "last_node": err.last_node,
            "workflow_name": err.workflow_name,
            "alerted": should_alert,
        },
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["workflow_key", "n8n_execution_id"],
        set_={"status": "failed", "finished_at": now, "error_message": err.message},
    )
    db.execute(stmt)
    db.commit()
    subject = f"Replyline automation failed: {err.workflow_name or err.workflow_key}"
    text = (
        f"Workflow: {err.workflow_name or err.workflow_key}\n"
        f"Step: {err.last_node or 'unknown'}\n"
        f"Error: {(err.message or 'no message')[:300]}\n"
        f"Execution: {err.n8n_execution_id}\n"
        "Leads are safe: the backend keeps every lead and retries delivery."
    )
    return {"should_alert": should_alert, "subject": subject, "text": text}


# ---------------------------------------------------------------- W3 notifications


class NotificationLogIn(BaseModel):
    lead_id: uuid.UUID | None = None
    channel: Literal["email", "telegram"]
    status: Literal["sent", "failed"]
    n8n_execution_id: str | None = Field(default=None, max_length=40)
    error: str | None = Field(default=None, max_length=500)


@router.post("/notifications/log")
def log_notification(n: NotificationLogIn, org: ServiceOrg, db: DbSession) -> dict:
    """Record an alert on the lead's timeline. A failed alert never touches the lead's data; it
    asks n8n to tell the admin (throttled like W9), so a broken Telegram bot is noticed."""
    from app.services.activity import record

    if n.lead_id is not None:
        owned = db.scalar(
            select(Lead.id).where(Lead.id == n.lead_id, Lead.organization_id == org.id)
        )
        if owned is None:
            raise HTTPException(404, "Lead not found.")
        record(
            db,
            org.id,
            n.lead_id,
            f"alert_{n.status}",
            "workflow",
            None,
            channel=n.channel,
            error=(n.error or "")[:200] or None,
        )
    db.commit()
    if n.status == "sent":
        return {"should_alert": False}
    err = WorkflowErrorIn(
        workflow_key=f"alert-{n.channel}",
        workflow_name=f"High-priority alert via {n.channel}",
        n8n_execution_id=n.n8n_execution_id or f"notif-{uuid.uuid4().hex[:12]}",
        last_node=f"Send {n.channel}",
        message=n.error or f"{n.channel} alert failed",
    )
    return log_workflow_error(err, org, db)


# ---------------------------------------------------------------- P8: W5, W6, W7, W9b


@router.get("/follow-ups/due")
def internal_due_follow_ups(org: ServiceOrg, db: DbSession) -> dict:
    """W5: due follow-ups, only while the organization is inside its own business hours."""
    from app.services import followups

    items = followups.due_follow_ups(db, org_id=org.id)
    return {"items": [{"id": str(f.id), "lead_id": str(f.lead_id)} for f in items]}


@router.post("/follow-ups/{fu_id}/prepare")
def internal_prepare_follow_up(fu_id: uuid.UUID, org: ServiceOrg, db: DbSession) -> dict:
    """W5: check the rules; skip with a reason or write a draft for approval. Never sends."""
    from app.models import FollowUp
    from app.services import followups

    f = db.scalar(select(FollowUp).where(FollowUp.id == fu_id, FollowUp.organization_id == org.id))
    if f is None:
        raise HTTPException(404, "Follow-up not found.")
    return followups.prepare(db, f)


@router.get("/leads/recovery-candidates")
def internal_recovery_candidates(org: ServiceOrg, db: DbSession) -> dict:
    from app.services import followups

    leads = followups.recovery_candidates(db, org.id)
    return {
        "items": [{"lead_id": str(x.id), "reason": followups.recovery_reason(db, x)} for x in leads]
    }


@router.post("/leads/{lead_id}/recovery-suggestion")
def internal_recovery_suggestion(lead_id: uuid.UUID, org: ServiceOrg, db: DbSession) -> dict:
    """W6: a gentle check-in draft for a quiet lead, into the Approvals queue."""
    from app.services import followups

    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if lead is None:
        raise HTTPException(404, "Lead not found.")
    return followups.recovery_suggestion(db, lead)


@router.post("/duplicates/scan")
def internal_duplicate_scan(org: ServiceOrg, db: DbSession) -> dict:
    """W7: find new duplicate pairs. Never merges; a person reviews them."""
    from app.services import duplicates

    added = duplicates.scan(db, org.id)
    link = f"{get_settings().frontend_public_url.rstrip('/')}/duplicates"
    return {
        "added": added,
        "notify": added > 0,
        "subject": f"Replyline: {added} possible duplicate lead pair(s) to review",
        "text": f"{added} new possible duplicate pair(s) were found. Nothing was merged.\n"
        f"Review them here: {link}",
    }


@router.post("/leads/retry-ai")
def internal_retry_ai(org: ServiceOrg, db: DbSession) -> dict:
    """W9b: retry failed analyses that are due and re-queue leads stuck by a crash (capped)."""
    from app.services.analysis import requeue_stuck_leads, retry_failed

    return {"requeued_stuck": requeue_stuck_leads(db), "recovered": retry_failed(db)}


# ---------------------------------------------------------------- W8, W10 reports


@router.get("/reports/daily")
def internal_daily_report(org: ServiceOrg, db: DbSession) -> dict:
    """W8 (hourly): a report only when the organization's local time is 08:30-09:29 and today's
    snapshot does not exist yet; otherwise {report: null}."""
    from app.services import reports

    now = datetime.now(UTC)
    if not reports.daily_due(org, now):
        return {"report": None}
    before = db.scalar(
        select(func.count())
        .select_from(ReportSnapshot)
        .where(ReportSnapshot.organization_id == org.id, ReportSnapshot.kind == "daily")
    )
    snap = reports.make_daily(db, org, now)
    after = db.scalar(
        select(func.count())
        .select_from(ReportSnapshot)
        .where(ReportSnapshot.organization_id == org.id, ReportSnapshot.kind == "daily")
    )
    if after == before:
        return {"report": None}  # already sent today
    link = f"{get_settings().frontend_public_url.rstrip('/')}/analytics"
    return {"report": reports.as_email(snap, org, link)}


@router.get("/reports/source-performance")
def internal_source_report(org: ServiceOrg, db: DbSession) -> dict:
    """W10 (hourly): weekly, Monday 08:30-09:29 local time, once."""
    from app.services import reports

    now = datetime.now(UTC)
    if not reports.weekly_due(org, now):
        return {"report": None}
    before = db.scalar(
        select(func.count())
        .select_from(ReportSnapshot)
        .where(
            ReportSnapshot.organization_id == org.id, ReportSnapshot.kind == "source_performance"
        )
    )
    snap = reports.make_source_performance(db, org, now)
    after = db.scalar(
        select(func.count())
        .select_from(ReportSnapshot)
        .where(
            ReportSnapshot.organization_id == org.id, ReportSnapshot.kind == "source_performance"
        )
    )
    if after == before:
        return {"report": None}
    link = f"{get_settings().frontend_public_url.rstrip('/')}/analytics"
    return {"report": reports.as_email(snap, org, link)}
