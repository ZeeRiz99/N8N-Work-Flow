"""Drafts and approvals for logged-in members (master prompt §7: drafts & approvals)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import literal, select

from app.api.deps import DbSession, UserDep, client_ip, csrf_protect
from app.models import CommunicationDraft, Lead, Organization
from app.repositories.tenant import get_owned
from app.services import approvals, assistant, drafting

router = APIRouter(tags=["drafts"], dependencies=[Depends(csrf_protect)])


class SaveDraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: Literal["professional", "friendly", "concise", "sales"] | None = None
    kind: Literal["first_reply", "follow_up"] = "first_reply"


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=300)


def _can_approve(user, org: Organization) -> None:
    allowed = (org.settings or {}).get("members_can_approve", True)
    if not (allowed or user.at_least("admin")):
        raise HTTPException(403, "Your role does not allow approving drafts.")


@router.post("/leads/{lead_id}/drafts", status_code=201)
def create_draft(lead_id: uuid.UUID, body: SaveDraftIn, user: UserDep, db: DbSession) -> dict:
    """Write a draft and put it in the Approvals queue (pending approval). Nothing is sent."""
    lead = get_owned(db, Lead, lead_id, user.organization_id)
    org = db.get(Organization, user.organization_id)
    if body.kind == "follow_up" and not assistant.follow_up_status(db, lead)["eligible"]:
        raise HTTPException(409, "No follow-up now: the follow-up rules are not met.")
    style = body.style or assistant.ai_settings(org)["default_style"]
    try:
        d = drafting.generate_draft(db, org.id, lead.id, style, user.user_id, kind=body.kind)
    except drafting.DraftRefused as exc:
        raise HTTPException(409, str(exc)) from exc
    row = approvals.save_generated(db, org.id, lead, d, user.user_id)
    db.commit()
    return {**approvals.draft_out(row, lead), "note": d.get("note")}


@router.get("/drafts")
def list_drafts(
    user: UserDep,
    db: DbSession,
    status: Literal[
        "pending_approval", "approved", "sending", "sent", "failed", "rejected", "all"
    ] = "pending_approval",
    lead_id: uuid.UUID | None = None,
) -> list[dict]:
    stmt = (
        select(CommunicationDraft, Lead)
        .join(Lead, Lead.id == CommunicationDraft.lead_id)
        .where(CommunicationDraft.organization_id == user.organization_id)
        .order_by(
            # The queue is worked highest score first (mockup 03); history newest first.
            Lead.score.desc().nulls_last() if status == "pending_approval" else literal(0),
            CommunicationDraft.created_at.desc(),
        )
        .limit(200)
    )
    if status != "all":
        stmt = stmt.where(CommunicationDraft.status == status)
    if lead_id:
        stmt = stmt.where(CommunicationDraft.lead_id == lead_id)
    return [approvals.draft_out(d, lead) for d, lead in db.execute(stmt).all()]


def _get(db, user, draft_id) -> CommunicationDraft:
    return get_owned(db, CommunicationDraft, draft_id, user.organization_id)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: uuid.UUID, user: UserDep, db: DbSession) -> dict:
    d = _get(db, user, draft_id)
    return approvals.draft_out(d, db.get(Lead, d.lead_id))


@router.patch("/drafts/{draft_id}")
def edit_draft(draft_id: uuid.UUID, body: EditIn, user: UserDep, db: DbSession) -> dict:
    d = _get(db, user, draft_id)
    try:
        approvals.edit(db, d, body.subject, body.body, user.user_id)
    except approvals.DraftStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return approvals.draft_out(d, db.get(Lead, d.lead_id))


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: uuid.UUID, request: Request, user: UserDep, db: DbSession) -> dict:
    d = _get(db, user, draft_id)
    _can_approve(user, db.get(Organization, user.organization_id))
    try:
        approvals.approve(db, d, user.user_id, client_ip(request))
    except approvals.DraftStateError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    worker = getattr(request.app.state, "outbox", None)
    if worker is not None:
        worker.nudge()
    return approvals.draft_out(d, db.get(Lead, d.lead_id))


@router.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: uuid.UUID, body: RejectIn, user: UserDep, db: DbSession) -> dict:
    d = _get(db, user, draft_id)
    try:
        approvals.reject(db, d, body.reason, user.user_id)
    except approvals.DraftStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return approvals.draft_out(d, db.get(Lead, d.lead_id))
