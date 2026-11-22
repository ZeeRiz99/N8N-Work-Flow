"""Lead management for dashboard users: create, edit, stage, assign, archive, erase, notes.

All functions take the caller's organization id and only touch that organization's rows.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Lead,
    LeadInquiry,
    LeadNote,
    Organization,
    OrganizationMember,
    OutboxEvent,
    PipelineStage,
)
from app.repositories.tenant import get_owned
from app.services.activity import audit, record
from app.services.leads import _event_envelope
from app.services.normalize import normalize_email, normalize_phone
from app.services.org import source_id, stage_id


@dataclass(frozen=True)
class CreateResult:
    lead: Lead
    merged: bool  # True when an existing lead matched by email or phone


def find_existing(
    db: Session, org_id: uuid.UUID, email_n: str | None, phone_e164: str | None
) -> Lead | None:
    """Exact matches only (master prompt §6): normalized email first, then E.164 phone."""
    if not email_n and not phone_e164:
        return None
    conds = []
    if email_n:
        conds.append(Lead.email_normalized == email_n)
    if phone_e164:
        conds.append(Lead.phone_e164 == phone_e164)
    rows = db.scalars(
        select(Lead).where(Lead.organization_id == org_id, Lead.archived_at.is_(None), or_(*conds))
    ).all()
    by_email = next((r for r in rows if email_n and r.email_normalized == email_n), None)
    return by_email or (rows[0] if rows else None)


def create_lead(
    db: Session,
    org: Organization,
    actor_id: uuid.UUID | None,
    *,
    full_name: str,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
    website: str | None = None,
    message: str | None = None,
    source_key: str = "manual",
    channel: str = "manual",
    actor_type: str = "user",
    analyze: bool = True,
) -> CreateResult:
    email_n = normalize_email(email)
    phone_e = normalize_phone(phone, org.default_country)
    existing = find_existing(db, org.id, email_n, phone_e)
    if existing is not None:
        existing.phone_raw = existing.phone_raw or phone or None
        existing.phone_e164 = existing.phone_e164 or phone_e
        existing.company = existing.company or company or None
        existing.website = existing.website or website or None
        existing.last_interaction_at = datetime.now(UTC)
        lead, merged = existing, True
    else:
        lead = Lead(
            organization_id=org.id,
            full_name=full_name,
            email=email or None,
            email_normalized=email_n,
            phone_raw=phone or None,
            phone_e164=phone_e,
            company=company or None,
            website=website or None,
            stage_id=stage_id(db, org.id, "new"),
            source_id=source_id(db, org.id, source_key),
            ai_status="pending" if (message and analyze) else "skipped",
        )
        db.add(lead)
        db.flush()
        merged = False
    record(
        db,
        org.id,
        lead.id,
        "lead_merged" if merged else "lead_created",
        actor_type,
        actor_id,
        source=source_key,
    )

    if message:
        inquiry = LeadInquiry(
            organization_id=org.id, lead_id=lead.id, message=message, channel=channel
        )
        db.add(inquiry)
        db.flush()
        record(db, org.id, lead.id, "inquiry_received", actor_type, actor_id, channel=channel)
        if analyze:
            lead.ai_status = "pending"
            db.add(
                OutboxEvent(
                    organization_id=org.id,
                    event_type="lead.created",
                    payload=_event_envelope(
                        "lead.created",
                        org.id,
                        {
                            "lead_id": str(lead.id),
                            "inquiry_id": str(inquiry.id),
                            "new_lead": not merged,
                        },
                    ),
                )
            )
    db.flush()
    return CreateResult(lead, merged)


def update_lead(
    db: Session, org: Organization, lead: Lead, actor_id: uuid.UUID, data: dict
) -> None:
    changed = []
    if "email" in data:
        new_n = normalize_email(data["email"])
        if new_n and new_n != lead.email_normalized:
            clash = db.scalar(
                select(Lead.id).where(
                    Lead.organization_id == org.id,
                    Lead.email_normalized == new_n,
                    Lead.archived_at.is_(None),
                    Lead.id != lead.id,
                )
            )
            if clash:
                raise HTTPException(409, "Another lead already uses this email.")
        lead.email, lead.email_normalized = data["email"] or None, new_n
        changed.append("email")
    if "phone" in data:
        lead.phone_raw = data["phone"] or None
        lead.phone_e164 = normalize_phone(data["phone"], org.default_country)
        changed.append("phone")
    for field in ("full_name", "company", "website", "do_not_contact", "custom_fields"):
        if field in data:
            setattr(lead, field, data[field])
            changed.append(field)
    if changed:
        record(db, org.id, lead.id, "lead_updated", "user", actor_id, fields=sorted(changed))


def change_stage(
    db: Session, org_id: uuid.UUID, lead: Lead, new_stage_id: uuid.UUID, actor_id: uuid.UUID
) -> PipelineStage:
    stage = get_owned(db, PipelineStage, new_stage_id, org_id)
    if lead.stage_id == stage.id:
        return stage
    old = db.get(PipelineStage, lead.stage_id) if lead.stage_id else None
    lead.stage_id = stage.id
    record(
        db,
        org_id,
        lead.id,
        "stage_changed",
        "user",
        actor_id,
        from_stage=old.key if old else None,
        to_stage=stage.key,
        to_label=stage.label,
    )
    return stage


def assign(
    db: Session, org_id: uuid.UUID, lead: Lead, user_id: uuid.UUID | None, actor_id: uuid.UUID
) -> None:
    if user_id is not None:
        member = db.scalar(
            select(OrganizationMember.id).where(
                OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id
            )
        )
        if member is None:
            raise HTTPException(422, "That person is not a member of this organization.")
    if lead.assigned_to == user_id:
        return
    lead.assigned_to = user_id
    record(
        db,
        org_id,
        lead.id,
        "assigned" if user_id else "unassigned",
        "user",
        actor_id,
        assignee=str(user_id) if user_id else None,
    )


def archive(db: Session, org_id: uuid.UUID, lead: Lead, actor_id: uuid.UUID) -> None:
    if lead.archived_at is None:
        lead.archived_at = datetime.now(UTC)
        record(db, org_id, lead.id, "archived", "user", actor_id)


def restore(db: Session, org_id: uuid.UUID, lead: Lead, actor_id: uuid.UUID) -> None:
    if lead.archived_at is None:
        return
    if lead.email_normalized:
        clash = db.scalar(
            select(Lead.id).where(
                Lead.organization_id == org_id,
                Lead.email_normalized == lead.email_normalized,
                Lead.archived_at.is_(None),
                Lead.id != lead.id,
            )
        )
        if clash:
            raise HTTPException(409, "An active lead already uses this email. Merge instead.")
    lead.archived_at = None
    record(db, org_id, lead.id, "restored", "user", actor_id)


def erase(db: Session, org_id: uuid.UUID, lead: Lead, actor_id: uuid.UUID, ip: str | None) -> None:
    """Remove the lead and everything attached (cascade). The audit row keeps no personal data."""
    lead_id = lead.id
    db.delete(lead)
    audit(db, org_id, actor_id, "lead.erased", "lead", lead_id, ip=ip)


def add_note(
    db: Session, org_id: uuid.UUID, lead: Lead, body: str, author_id: uuid.UUID
) -> LeadNote:
    note = LeadNote(organization_id=org_id, lead_id=lead.id, author_id=author_id, body=body)
    db.add(note)
    db.flush()
    record(db, org_id, lead.id, "note_added", "user", author_id, note_id=str(note.id))
    return note
