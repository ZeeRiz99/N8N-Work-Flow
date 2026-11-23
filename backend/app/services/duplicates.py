"""Fuzzy duplicate detection and human-approved merging.

Exact email/phone matches are merged at intake (crm.find_existing). This module finds the
uncertain ones (similar name and company, different or missing contact details) and lists them
for a person to merge or dismiss.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Lead, LeadActivity, LeadInquiry, LeadNote
from app.models.duplicates import DuplicateCandidate
from app.repositories.tenant import get_owned
from app.services.activity import audit, record

NAME_THRESHOLD = 0.6
COMPANY_THRESHOLD = 0.6


def scan(db: Session, org_id: uuid.UUID) -> int:
    """Find similar active pairs in one organization. Returns how many new candidates were added.
    Dismissed and merged pairs are never re-suggested (the unique pair already exists)."""
    rows = db.execute(
        text(
            """
            SELECT a.id, b.id,
                   similarity(a.full_name, b.full_name) AS name_sim,
                   similarity(coalesce(a.company, ''), coalesce(b.company, '')) AS company_sim
            FROM leads a
            JOIN leads b
              ON b.organization_id = a.organization_id
             AND a.id < b.id
             AND a.full_name % b.full_name
            WHERE a.organization_id = :org
              AND a.archived_at IS NULL AND b.archived_at IS NULL
            """
        ),
        {"org": org_id},
    ).all()
    added = 0
    for a_id, b_id, name_sim, company_sim in rows:
        reasons = []
        if name_sim >= NAME_THRESHOLD:
            reasons.append({"field": "full_name", "similarity": round(name_sim, 2)})
        if company_sim >= COMPANY_THRESHOLD:
            reasons.append({"field": "company", "similarity": round(company_sim, 2)})
        if len(reasons) < 2 and not (name_sim >= 0.85):
            continue  # a similar name alone is too weak unless it is nearly identical
        confidence = round(max(name_sim, (name_sim + company_sim) / 2), 2)
        inserted = db.scalar(
            insert(DuplicateCandidate)
            .values(
                organization_id=org_id,
                lead_a_id=a_id,
                lead_b_id=b_id,
                confidence=confidence,
                reasons=reasons,
            )
            .on_conflict_do_nothing(index_elements=["organization_id", "lead_a_id", "lead_b_id"])
            .returning(DuplicateCandidate.id)
        )
        added += inserted is not None
    db.commit()
    return added


def merge(
    db: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, keep_id: uuid.UUID, actor_id: uuid.UUID
) -> Lead:
    """Keep one lead, move the other's inquiries, notes and timeline onto it, fill empty fields,
    then archive the merged-away lead (archived, not deleted, so the merge can be audited)."""
    cand = get_owned(db, DuplicateCandidate, candidate_id, org_id)
    if cand.status != "open":
        raise HTTPException(409, "This pair has already been reviewed.")
    if keep_id not in (cand.lead_a_id, cand.lead_b_id):
        raise HTTPException(422, "Keep one of the two leads in this pair.")
    drop_id = cand.lead_b_id if keep_id == cand.lead_a_id else cand.lead_a_id
    keep = get_owned(db, Lead, keep_id, org_id)
    drop = get_owned(db, Lead, drop_id, org_id)

    for model in (LeadInquiry, LeadNote, LeadActivity):
        db.execute(
            update(model)
            .where(model.lead_id == drop.id, model.organization_id == org_id)
            .values(lead_id=keep.id)
        )
    for attr in ("company", "website", "phone_raw", "phone_e164", "assigned_to"):
        if getattr(keep, attr) is None and getattr(drop, attr) is not None:
            setattr(keep, attr, getattr(drop, attr))
    if keep.email_normalized is None and drop.email_normalized is not None:
        email, email_n = drop.email, drop.email_normalized
        drop.email = drop.email_normalized = None  # free the unique email before moving it
        db.flush()
        keep.email, keep.email_normalized = email, email_n
    keep.do_not_contact = keep.do_not_contact or drop.do_not_contact
    keep.first_inquiry_at = min(keep.first_inquiry_at, drop.first_inquiry_at)
    keep.last_interaction_at = max(keep.last_interaction_at, drop.last_interaction_at)
    drop.archived_at = func.now()
    cand.status, cand.reviewed_by = "merged", actor_id
    record(db, org_id, keep.id, "lead_merged", "user", actor_id, merged_lead=str(drop.id))
    audit(db, org_id, actor_id, "lead.merged", "lead", keep.id, merged_lead=str(drop.id))
    db.commit()
    return keep


def dismiss(db: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    cand = get_owned(db, DuplicateCandidate, candidate_id, org_id)
    if cand.status != "open":
        raise HTTPException(409, "This pair has already been reviewed.")
    cand.status, cand.reviewed_by = "dismissed", actor_id
    db.commit()


def open_candidates(db: Session, org_id: uuid.UUID) -> list[DuplicateCandidate]:
    return list(
        db.scalars(
            select(DuplicateCandidate)
            .where(
                DuplicateCandidate.organization_id == org_id, DuplicateCandidate.status == "open"
            )
            .order_by(DuplicateCandidate.confidence.desc())
        )
    )


MERGE_FIELDS = ("full_name", "email", "phone_raw", "company", "website", "assigned_to")


def preview(db: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, keep_id: uuid.UUID) -> dict:
    """What a merge would produce, without changing anything: the kept lead's fields after
    gap-filling, and how many records move over. The same rules as merge()."""
    cand = get_owned(db, DuplicateCandidate, candidate_id, org_id)
    if keep_id not in (cand.lead_a_id, cand.lead_b_id):
        raise HTTPException(422, "Keep one of the two leads in this pair.")
    drop_id = cand.lead_b_id if keep_id == cand.lead_a_id else cand.lead_a_id
    keep = get_owned(db, Lead, keep_id, org_id)
    drop = get_owned(db, Lead, drop_id, org_id)
    fields = []
    for attr in MERGE_FIELDS:
        kept, other = getattr(keep, attr), getattr(drop, attr)
        filled = kept is None and other is not None and attr != "full_name"
        fields.append(
            {
                "field": attr,
                "keep": str(kept) if kept is not None else None,
                "other": str(other) if other is not None else None,
                "result": str(other if filled else kept) if (other if filled else kept) else None,
                "source": "other" if filled else "keep",
            }
        )

    def moved(model) -> int:
        return (
            db.scalar(select(func.count()).select_from(model).where(model.lead_id == drop.id)) or 0
        )

    return {
        "keep_id": str(keep.id),
        "drop_id": str(drop.id),
        "fields": fields,
        "moves": {
            "messages": moved(LeadInquiry),
            "notes": moved(LeadNote),
            "timeline_entries": moved(LeadActivity),
        },
        "do_not_contact": keep.do_not_contact or drop.do_not_contact,
        "archived_after": drop.full_name,
    }
