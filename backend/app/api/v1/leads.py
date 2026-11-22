"""Dashboard reads for logged-in members of an organization."""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, UserDep
from app.models import Lead, LeadInquiry, WorkflowExecution

router = APIRouter(tags=["leads"])


@router.get("/leads")
def list_leads(
    user: UserDep,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    total = db.scalar(
        select(func.count()).select_from(Lead).where(Lead.organization_id == user.organization_id)
    )
    latest_msg = (
        select(LeadInquiry.message)
        .where(LeadInquiry.lead_id == Lead.id)
        .order_by(LeadInquiry.received_at.desc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    inquiry_count = (
        select(func.count()).where(LeadInquiry.lead_id == Lead.id).correlate(Lead).scalar_subquery()
    )
    rows = db.execute(
        select(Lead, latest_msg.label("latest_message"), inquiry_count.label("inquiries"))
        .where(Lead.organization_id == user.organization_id, Lead.archived_at.is_(None))
        .order_by(Lead.last_interaction_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": str(lead.id),
            "full_name": lead.full_name,
            "company": lead.company,
            "email": lead.email,
            "priority": lead.priority,
            "score": lead.score,
            "score_source": lead.score_source,
            "ai_status": lead.ai_status,
            "inquiries": count,
            "latest_message": " ".join((msg or "").split())[:160],
            "created_at": lead.created_at.isoformat(),
            "last_interaction_at": lead.last_interaction_at.isoformat(),
        }
        for lead, msg, count in rows
    ]
    return {"items": items, "total": total or 0, "page": page, "page_size": page_size}


@router.get("/automation/executions")
def list_executions(user: UserDep, db: DbSession, limit: int = Query(20, ge=1, le=100)) -> dict:
    rows = db.scalars(
        select(WorkflowExecution)
        .where(WorkflowExecution.organization_id == user.organization_id)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "items": [
            {
                "workflow_key": r.workflow_key,
                "n8n_execution_id": r.n8n_execution_id,
                "status": r.status,
                "lead_id": str(r.lead_id) if r.lead_id else None,
                "request_id": r.request_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }
