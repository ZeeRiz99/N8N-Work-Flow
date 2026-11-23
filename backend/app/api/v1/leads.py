"""Leads API for logged-in members. Every query is scoped to the caller's organization."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import aliased

from app.api.deps import AdminDep, DbSession, UserDep, client_ip, csrf_protect
from app.models import (
    Lead,
    LeadActivity,
    LeadInquiry,
    LeadNote,
    LeadSource,
    Organization,
    PipelineStage,
    User,
    WorkflowExecution,
)
from app.repositories.tenant import get_owned, scoped
from app.schemas.public import EMAIL_RE
from app.services import crm

router = APIRouter(tags=["leads"], dependencies=[Depends(csrf_protect)])

SORTS = {
    "recent": Lead.last_interaction_at.desc(),
    "newest": Lead.created_at.desc(),
    "score": Lead.score.desc().nulls_last(),
    "name": Lead.full_name.asc(),
}


def _check_email(v: str | None) -> str | None:
    if v and not EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address.")
    return v or None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LeadIn(Strict):
    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=4000)

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str | None) -> str | None:
        return _check_email(v)


class LeadPatch(Strict):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    do_not_contact: bool | None = None
    custom_fields: dict | None = None

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str | None) -> str | None:
        return _check_email(v)


class StageIn(Strict):
    stage_id: uuid.UUID


class AssignIn(Strict):
    user_id: uuid.UUID | None


class NoteIn(Strict):
    body: str = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------- shared row shape

Assignee = aliased(User)


def _rows_query(org_id: uuid.UUID):
    latest_msg = (
        select(LeadInquiry.message)
        .where(LeadInquiry.lead_id == Lead.id)
        .order_by(LeadInquiry.received_at.desc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    inquiries = (
        select(func.count()).where(LeadInquiry.lead_id == Lead.id).correlate(Lead).scalar_subquery()
    )
    return (
        select(
            Lead,
            PipelineStage.key,
            PipelineStage.label,
            LeadSource.label,
            Assignee.full_name,
            latest_msg.label("latest_message"),
            inquiries.label("inquiries"),
        )
        .outerjoin(
            PipelineStage,
            and_(PipelineStage.id == Lead.stage_id, PipelineStage.organization_id == org_id),
        )
        .outerjoin(
            LeadSource, and_(LeadSource.id == Lead.source_id, LeadSource.organization_id == org_id)
        )
        .outerjoin(Assignee, Assignee.id == Lead.assigned_to)
        .where(Lead.organization_id == org_id)
    )


def _row(lead, stage_key, stage_label, source_label, assignee_name, msg, count) -> dict:
    return {
        "id": str(lead.id),
        "full_name": lead.full_name,
        "company": lead.company,
        "email": lead.email,
        "phone": lead.phone_raw,
        "website": lead.website,
        "priority": lead.priority,
        "score": lead.score,
        "score_source": lead.score_source,
        "score_provisional": lead.score_provisional,
        "needs_review": lead.needs_review,
        "ai_status": lead.ai_status,
        "stage": {
            "id": str(lead.stage_id) if lead.stage_id else None,
            "key": stage_key,
            "label": stage_label,
        },
        "source": source_label,
        "assigned_to": (
            {"id": str(lead.assigned_to), "name": assignee_name} if lead.assigned_to else None
        ),
        "do_not_contact": lead.do_not_contact,
        "archived": lead.archived_at is not None,
        "inquiries": count,
        "latest_message": " ".join((msg or "").split())[:160],
        "created_at": lead.created_at.isoformat(),
        "last_interaction_at": lead.last_interaction_at.isoformat(),
    }


def _one(db, org_id: uuid.UUID, lead_id: uuid.UUID) -> dict:
    row = db.execute(_rows_query(org_id).where(Lead.id == lead_id)).first()
    return _row(*row)


# ---------------------------------------------------------------- list


@router.get("/leads")
def list_leads(
    user: UserDep,
    db: DbSession,
    q: str | None = Query(None, max_length=100, description="Name, company or email"),
    stage: str | None = Query(None, max_length=40, description="Stage key"),
    priority: Literal["high", "medium", "low", "unscored"] | None = None,
    source: str | None = Query(None, max_length=40, description="Source key"),
    assigned: str | None = Query(None, description="'me', 'none' or a user id"),
    ai_status: Literal["pending", "processing", "done", "failed", "skipped"] | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    archived: bool = False,
    sort: Literal["recent", "newest", "score", "name"] = "recent",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    org_id = user.organization_id
    stmt = _rows_query(org_id).where(
        Lead.archived_at.is_not(None) if archived else Lead.archived_at.is_(None)
    )
    if q:
        haystack = (
            func.coalesce(Lead.full_name, "")
            + literal(" ")
            + func.coalesce(Lead.company, "")
            + literal(" ")
            + func.coalesce(Lead.email, "")
        )
        # ILIKE uses the trigram GIN index. word_similarity compares the search with the best-
        # matching part of the text, so a one-letter typo ("Amira Hasan") still finds the lead.
        stmt = stmt.where(or_(haystack.ilike(f"%{q}%"), func.word_similarity(q, haystack) > 0.5))
    if stage:
        stmt = stmt.where(PipelineStage.key == stage)
    if priority:
        stmt = stmt.where(Lead.priority == priority)
    if source:
        stmt = stmt.where(LeadSource.key == source)
    if assigned == "me":
        stmt = stmt.where(Lead.assigned_to == user.user_id)
    elif assigned == "none":
        stmt = stmt.where(Lead.assigned_to.is_(None))
    elif assigned:
        try:
            stmt = stmt.where(Lead.assigned_to == uuid.UUID(assigned))
        except ValueError:
            stmt = stmt.where(literal(False))
    if ai_status:
        stmt = stmt.where(Lead.ai_status == ai_status)
    if created_from:
        stmt = stmt.where(Lead.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Lead.created_at < created_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(SORTS[sort], Lead.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_row(*r) for r in rows],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------- create / read / update


@router.post("/leads", status_code=201)
def create_lead(body: LeadIn, user: UserDep, db: DbSession, request: Request) -> dict:
    org = db.get(Organization, user.organization_id)
    result = crm.create_lead(
        db,
        org,
        user.user_id,
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        company=body.company,
        website=body.website,
        message=body.message,
    )
    db.commit()
    worker = getattr(request.app.state, "outbox", None)
    if worker is not None and body.message:
        worker.nudge()
    return {**_one(db, org.id, result.lead.id), "merged": result.merged}


@router.get("/leads/{lead_id}")
def get_lead(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    get_owned(db, Lead, lead_id, user.organization_id)
    return _one(db, user.organization_id, lead_id)


@router.patch("/leads/{lead_id}")
def patch_lead(lead_id: uuid.UUID, body: LeadPatch, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    org = db.get(Organization, user.organization_id)
    crm.update_lead(db, org, lead, user.user_id, body.model_dump(exclude_unset=True))
    db.commit()
    return _one(db, org.id, lead.id)


@router.post("/leads/{lead_id}/stage")
def set_stage(lead_id: uuid.UUID, body: StageIn, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    crm.change_stage(db, user.organization_id, lead, body.stage_id, user.user_id)
    db.commit()
    return _one(db, user.organization_id, lead.id)


@router.post("/leads/{lead_id}/assign")
def set_assignee(lead_id: uuid.UUID, body: AssignIn, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    crm.assign(db, user.organization_id, lead, body.user_id, user.user_id)
    db.commit()
    return _one(db, user.organization_id, lead.id)


@router.post("/leads/{lead_id}/archive")
def archive_lead(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    crm.archive(db, user.organization_id, lead, user.user_id)
    db.commit()
    return _one(db, user.organization_id, lead.id)


@router.post("/leads/{lead_id}/restore")
def restore_lead(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    crm.restore(db, user.organization_id, lead, user.user_id)
    db.commit()
    return _one(db, user.organization_id, lead.id)


@router.delete("/leads/{lead_id}", status_code=204)
def erase_lead(lead_id: uuid.UUID, user: AdminDep, db: DbSession, request: Request) -> None:
    """Admin-only erasure: removes the lead's personal data; an anonymous audit row remains."""
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    crm.erase(db, user.organization_id, lead, user.user_id, client_ip(request))
    db.commit()


# ---------------------------------------------------------------- notes, timeline, inquiries


@router.get("/leads/{lead_id}/notes")
def list_notes(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> list[dict]:
    get_owned(db, Lead, lead_id, user.organization_id)
    rows = db.execute(
        select(LeadNote, User.full_name)
        .outerjoin(User, User.id == LeadNote.author_id)
        .where(LeadNote.lead_id == lead_id, LeadNote.organization_id == user.organization_id)
        .order_by(LeadNote.created_at.desc())
    ).all()
    return [
        {"id": str(n.id), "body": n.body, "author": name, "created_at": n.created_at.isoformat()}
        for n, name in rows
    ]


@router.post("/leads/{lead_id}/notes", status_code=201)
def add_note(lead_id: uuid.UUID, body: NoteIn, user: UserDep, db: DbSession) -> dict:
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    note = crm.add_note(db, user.organization_id, lead, body.body, user.user_id)
    db.commit()
    return {
        "id": str(note.id),
        "body": note.body,
        "author": user.full_name,
        "created_at": note.created_at.isoformat(),
    }


@router.get("/leads/{lead_id}/activities")
def list_activities(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> list[dict]:
    get_owned(db, Lead, lead_id, user.organization_id)
    rows = db.execute(
        select(LeadActivity, User.full_name)
        .outerjoin(User, User.id == LeadActivity.actor_id)
        .where(
            LeadActivity.lead_id == lead_id,
            LeadActivity.organization_id == user.organization_id,
        )
        .order_by(LeadActivity.created_at.desc())
        .limit(200)
    ).all()
    return [
        {
            "id": str(a.id),
            "type": a.type,
            "actor_type": a.actor_type,
            "actor": name,
            "payload": a.payload,
            "created_at": a.created_at.isoformat(),
        }
        for a, name in rows
    ]


@router.get("/leads/{lead_id}/inquiries")
def list_inquiries(lead_id: uuid.UUID, user: UserDep, db: DbSession) -> list[dict]:
    get_owned(db, Lead, lead_id, user.organization_id)
    rows = db.scalars(
        scoped(LeadInquiry, user.organization_id)
        .where(LeadInquiry.lead_id == lead_id)
        .order_by(LeadInquiry.received_at.desc())
    ).all()
    return [
        {
            "id": str(i.id),
            "message": i.message,
            "channel": i.channel,
            "form_fields": i.form_fields,
            "received_at": i.received_at.isoformat(),
        }
        for i in rows
    ]


# ---------------------------------------------------------------- automation runs (read)


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
