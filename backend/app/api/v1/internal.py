"""Internal API for n8n only. Service key required; blocked at the reverse proxy in production.

The backend decides; n8n only sequences and delivers (D10).
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession, ServiceOrg
from app.core.config import get_settings
from app.models import Lead, LeadInquiry, WorkflowExecution
from app.services.analysis import analyze_lead
from app.services.outbox import redispatch_failed

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health")
def internal_health(org: ServiceOrg) -> dict:
    return {"status": "ok", "organization": org.slug}


@router.post("/leads/{lead_id}/analyze")
def analyze(lead_id: uuid.UUID, org: ServiceOrg, db: DbSession) -> dict:
    result = analyze_lead(db, org.id, lead_id)
    if result is None:
        raise HTTPException(404, "Lead not found.")
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
