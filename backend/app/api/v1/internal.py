"""Internal API for n8n only. Service key required; blocked at the reverse proxy in production.

The backend decides; n8n only sequences and delivers (D10).
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession, ServiceOrg
from app.core.config import get_settings
from app.models import Lead, LeadInquiry, WorkflowExecution
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
    count = redispatch_failed(db)
    worker = getattr(request.app.state, "outbox", None)
    if worker is not None:
        worker.nudge()
    return {"requeued": count}


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
