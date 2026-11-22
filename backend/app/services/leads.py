"""Lead intake: validate, normalize, dedupe, store, and announce through the outbox.

Everything for one submission happens in ONE transaction: the lead (or a new inquiry on an
existing lead), the idempotency record and the outbox event. Either all of it is saved or none.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models import IdempotencyKey, Lead, LeadInquiry, Organization, OutboxEvent
from app.schemas.public import PublicLeadIn
from app.services.normalize import normalize_email as _normalize_email
from app.services.normalize import normalize_phone
from app.services.org import source_id, stage_id

IDEMPOTENCY_SCOPE = "public_lead"


@dataclass(frozen=True)
class IntakeResult:
    lead_id: uuid.UUID
    inquiry_id: uuid.UUID
    created_lead: bool  # False when the email matched an existing lead
    replayed: bool  # True when this exact submission was already processed


def normalize_email(email: str) -> str:
    """Lowercase and trim. Gmail dots are kept on purpose (master prompt §6)."""
    return _normalize_email(email) or ""


def default_idempotency_key(org_id: uuid.UUID, email_normalized: str, message: str) -> str:
    """Same person + same message = same submission, so a double click creates nothing new."""
    raw = f"{org_id}|{email_normalized}|{' '.join(message.split())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _event_envelope(event: str, org_id: uuid.UUID, data: dict) -> dict:
    return {
        "event": event,
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "organization_id": str(org_id),
        "request_id": request_id_var.get(),
        "data": data,
    }


def ingest_public_lead(
    db: Session, org: Organization, data: PublicLeadIn, idempotency_key: str | None = None
) -> IntakeResult:
    email_n = normalize_email(data.email)
    key = idempotency_key or default_idempotency_key(org.id, email_n, data.message)

    replay = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.organization_id == org.id,
            IdempotencyKey.scope == IDEMPOTENCY_SCOPE,
            IdempotencyKey.key == key,
        )
    )
    if replay:
        return _replayed(replay)

    try:
        result = _store(db, org, data, email_n, key)
        db.commit()
        return result
    except IntegrityError:
        # A parallel request with the same key or email won the race; use its result.
        db.rollback()
        replay = db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.organization_id == org.id,
                IdempotencyKey.scope == IDEMPOTENCY_SCOPE,
                IdempotencyKey.key == key,
            )
        )
        if replay:
            return _replayed(replay)
        result = _store(db, org, data, email_n, key)  # email race: lead now exists, add inquiry
        db.commit()
        return result


def _replayed(row: IdempotencyKey) -> IntakeResult:
    return IntakeResult(
        lead_id=uuid.UUID(row.response["lead_id"]),
        inquiry_id=uuid.UUID(row.response["inquiry_id"]),
        created_lead=False,
        replayed=True,
    )


def _store(
    db: Session, org: Organization, data: PublicLeadIn, email_n: str, key: str
) -> IntakeResult:
    now = datetime.now(UTC)
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == org.id,
            Lead.email_normalized == email_n,
            Lead.archived_at.is_(None),
        )
    )
    created = lead is None
    if created:
        lead = Lead(
            organization_id=org.id,
            full_name=data.full_name,
            email=data.email,
            email_normalized=email_n,
            phone_raw=data.phone or None,
            phone_e164=normalize_phone(data.phone, org.default_country),
            company=data.company or None,
            stage_id=stage_id(db, org.id, "new"),
            source_id=source_id(db, org.id, "form"),
        )
        db.add(lead)
        db.flush()
    else:
        # Returning lead: fill gaps, never overwrite what we already know.
        lead.phone_raw = lead.phone_raw or data.phone or None
        lead.phone_e164 = lead.phone_e164 or normalize_phone(data.phone, org.default_country)
        lead.company = lead.company or data.company or None
        lead.last_interaction_at = now
        lead.ai_status = "pending"  # the new message gets analyzed too

    form_fields = {
        k: v
        for k, v in {
            "service": data.service,
            "budget": data.budget,
            "timeline": data.timeline,
        }.items()
        if v
    }
    inquiry = LeadInquiry(
        organization_id=org.id,
        lead_id=lead.id,
        message=data.message,
        channel="form",
        idempotency_key=key[:100],
        form_fields=form_fields,
    )
    db.add(inquiry)
    db.flush()

    db.add(
        IdempotencyKey(
            organization_id=org.id,
            scope=IDEMPOTENCY_SCOPE,
            key=key,
            response={"lead_id": str(lead.id), "inquiry_id": str(inquiry.id)},
        )
    )
    db.add(
        OutboxEvent(
            organization_id=org.id,
            event_type="lead.created",
            payload=_event_envelope(
                "lead.created",
                org.id,
                {"lead_id": str(lead.id), "inquiry_id": str(inquiry.id), "new_lead": created},
            ),
        )
    )
    db.flush()
    return IntakeResult(lead.id, inquiry.id, created_lead=created, replayed=False)
