"""Draft lifecycle (master prompt §5 F3, §8.4, D13): save, edit, approve, reject, send claim.

Safety rules enforced here, in one place:
- A draft can be sent only after a person approves it (status `approved`).
- The send path claims the draft atomically (approved -> sending); a second claim gets nothing,
  so a redelivered n8n event can never send twice.
- Approval needs every blocking check to pass, a contactable lead and a recipient address.
- The recipient is copied from the lead and never taken from user input.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.draft_checks import finalize_body, passed
from app.models import CommunicationDraft, CommunicationLog, Lead, OutboxEvent
from app.services.activity import audit, record
from app.services.drafting import recheck
from app.services.leads import _event_envelope

FOLLOW_UP_DAYS = 3


class DraftStateError(Exception):
    """The draft is not in a state that allows this action."""


def save_generated(
    db: Session, org_id: uuid.UUID, lead: Lead, draft: dict, actor_id: uuid.UUID | None
) -> CommunicationDraft:
    """Store a generated draft as pending approval; older open drafts of the same kind for the
    lead are cancelled, so the queue holds one draft per lead and kind."""
    db.execute(
        update(CommunicationDraft)
        .where(
            CommunicationDraft.lead_id == lead.id,
            CommunicationDraft.kind == draft.get("kind", "first_reply"),
            CommunicationDraft.status.in_(("draft", "pending_approval")),
        )
        .values(status="cancelled")
    )
    row = CommunicationDraft(
        organization_id=org_id,
        lead_id=lead.id,
        kind=draft.get("kind", "first_reply"),
        to_address=lead.email,
        subject=draft["subject"],
        body=draft["body"],
        style=draft["style"],
        status="pending_approval",
        checks=draft["checks"],
        services_mentioned=draft.get("services_mentioned", []),
        source=draft["source"],
        model=draft.get("model"),
        created_by=actor_id,
    )
    db.add(row)
    db.flush()
    return row


def _open(draft: CommunicationDraft) -> None:
    if draft.status != "pending_approval":
        raise DraftStateError(f"This draft is {draft.status.replace('_', ' ')}.")


def edit(
    db: Session, draft: CommunicationDraft, subject: str, body: str, actor_id: uuid.UUID
) -> CommunicationDraft:
    _open(draft)
    checks = recheck(
        db, draft.organization_id, draft.lead_id, subject, body, draft.services_mentioned
    )
    draft.subject, draft.body = subject, finalize_body(body)
    draft.checks, draft.edited = checks, True
    record(
        db,
        draft.organization_id,
        draft.lead_id,
        "draft_edited",
        "user",
        actor_id,
        draft_id=str(draft.id),
    )
    return draft


def approve(
    db: Session, draft: CommunicationDraft, actor_id: uuid.UUID, ip: str | None = None
) -> CommunicationDraft:
    _open(draft)
    lead = db.get(Lead, draft.lead_id)
    # Rerun the checks at approval time: the lead (do-not-contact, email) may have changed.
    draft.checks = recheck(
        db,
        draft.organization_id,
        draft.lead_id,
        draft.subject,
        draft.body,
        draft.services_mentioned,
    )
    if not passed(draft.checks):
        failing = [c["label"] for c in draft.checks if not c["ok"] and c["severity"] == "fail"]
        raise DraftStateError("Fix these checks first: " + "; ".join(failing) + ".")
    if lead is None or lead.do_not_contact or not lead.email:
        raise DraftStateError("This lead cannot be contacted.")
    from app.services.followups import is_suppressed

    if is_suppressed(db, draft.organization_id, lead.email):
        raise DraftStateError("This address is on the suppression list.")
    draft.to_address = lead.email  # always the lead's current address
    draft.status, draft.approved_by, draft.approved_at = "approved", actor_id, datetime.now(UTC)
    db.add(
        OutboxEvent(
            organization_id=draft.organization_id,
            event_type="draft.approved",
            payload=_event_envelope(
                "draft.approved",
                draft.organization_id,
                {"draft_id": str(draft.id), "lead_id": str(draft.lead_id)},
            ),
        )
    )
    audit(
        db,
        draft.organization_id,
        actor_id,
        "draft.approved",
        "communication_draft",
        draft.id,
        ip,
        edited=draft.edited,
        kind=draft.kind,
    )
    record(
        db,
        draft.organization_id,
        draft.lead_id,
        "draft_approved",
        "user",
        actor_id,
        draft_id=str(draft.id),
    )
    return draft


def reject(
    db: Session, draft: CommunicationDraft, reason: str, actor_id: uuid.UUID
) -> CommunicationDraft:
    _open(draft)
    draft.status, draft.rejection_reason = "rejected", reason
    record(
        db,
        draft.organization_id,
        draft.lead_id,
        "draft_rejected",
        "user",
        actor_id,
        draft_id=str(draft.id),
        reason=reason,
    )
    return draft


# ---------------------------------------------------------------- send path (n8n W4b)


def claim_send(db: Session, org_id: uuid.UUID, draft_id: uuid.UUID) -> CommunicationDraft | None:
    """The ONLY way to obtain a draft for sending. Atomic: approved -> sending. Returns None if
    the draft is missing, not approved, or already claimed (n8n treats that as "stop")."""
    claimed = db.scalar(
        update(CommunicationDraft)
        .where(
            CommunicationDraft.id == draft_id,
            CommunicationDraft.organization_id == org_id,
            CommunicationDraft.status == "approved",
        )
        .values(status="sending")
        .returning(CommunicationDraft.id)
    )
    if not claimed:
        db.commit()
        return None
    draft = db.get(CommunicationDraft, claimed)
    # The suppression list is honoured by every send path, also after approval.
    from app.services.followups import is_suppressed

    if is_suppressed(db, org_id, draft.to_address):
        draft.status, draft.send_error = "cancelled", "address suppressed after approval"
        db.commit()
        return None
    db.commit()
    return draft


def _sending(db: Session, org_id: uuid.UUID, draft_id: uuid.UUID) -> CommunicationDraft:
    draft = db.scalar(
        select(CommunicationDraft).where(
            CommunicationDraft.id == draft_id, CommunicationDraft.organization_id == org_id
        )
    )
    if draft is None or draft.status != "sending":
        raise DraftStateError("Draft is not being sent.")
    return draft


def mark_sent(
    db: Session, org_id: uuid.UUID, draft_id: uuid.UUID, provider_message_id: str | None
) -> CommunicationDraft:
    draft = _sending(db, org_id, draft_id)
    now = datetime.now(UTC)
    draft.status, draft.sent_at = "sent", now
    db.add(
        CommunicationLog(
            organization_id=org_id,
            lead_id=draft.lead_id,
            draft_id=draft.id,
            direction="out",
            channel=draft.channel,
            provider="smtp",
            provider_message_id=provider_message_id,
            status="sent",
            occurred_at=now,
        )
    )
    lead = db.get(Lead, draft.lead_id)
    if lead is not None:
        lead.last_interaction_at = now
    db.flush()
    # Close the follow-up this email answered; schedule the next one if the rules allow (P8).
    from app.services.followups import on_sent

    on_sent(db, draft, now)
    record(
        db,
        org_id,
        draft.lead_id,
        "email_sent",
        "workflow",
        None,
        draft_id=str(draft.id),
        subject=draft.subject,
    )
    db.commit()
    return draft


def mark_failed(
    db: Session, org_id: uuid.UUID, draft_id: uuid.UUID, error: str
) -> CommunicationDraft:
    draft = _sending(db, org_id, draft_id)
    now = datetime.now(UTC)
    draft.status, draft.send_error = "failed", error[:300]
    db.add(
        CommunicationLog(
            organization_id=org_id,
            lead_id=draft.lead_id,
            draft_id=draft.id,
            direction="out",
            channel=draft.channel,
            provider="smtp",
            status="failed",
            error=error[:300],
            occurred_at=now,
        )
    )
    record(db, org_id, draft.lead_id, "email_failed", "workflow", None, draft_id=str(draft.id))
    db.commit()
    return draft


def draft_out(d: CommunicationDraft, lead: Lead | None = None) -> dict:
    return {
        "id": str(d.id),
        "lead_id": str(d.lead_id),
        "lead_name": lead.full_name if lead else None,
        "lead_company": lead.company if lead else None,
        "lead_score": lead.score if lead else None,
        "lead_priority": lead.priority if lead else None,
        "kind": d.kind,
        "to": d.to_address,
        "subject": d.subject,
        "body": d.body,
        "style": d.style,
        "status": d.status,
        "checks": d.checks,
        "all_passed": passed(d.checks),
        "source": d.source,
        "model": d.model,
        "edited": d.edited,
        "rejection_reason": d.rejection_reason,
        "send_error": d.send_error,
        "created_at": d.created_at.isoformat(),
        "approved_at": d.approved_at.isoformat() if d.approved_at else None,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
    }
