"""Follow-ups, suppression, recovery (master prompt §8.5, P8).

One function decides whether a lead may be contacted (`contact_check`). Every outbound path uses
it: follow-up preparation, recovery suggestions, approval and the send claim. The AI only writes
wording; it never decides to contact anyone.
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    CommunicationDraft,
    CommunicationLog,
    FollowUp,
    Lead,
    Organization,
    PipelineStage,
    Suppression,
)
from app.services.activity import record

MAX_ATTEMPTS = 3  # first reply + 2 follow-ups
COOLDOWN_DAYS = 3
BUSINESS_START, BUSINESS_END = time(9, 0), time(17, 0)  # local time, Monday to Friday
RECOVERY_AFTER_DAYS = 14
RECOVERY_COOLDOWN_DAYS = 30


def _org_settings(org: Organization) -> dict:
    return (org.settings or {}).get("follow_ups", {})


def is_suppressed(db: Session, org_id: uuid.UUID, email: str | None) -> str | None:
    if not email:
        return None
    return db.scalar(
        select(Suppression.reason).where(
            Suppression.organization_id == org_id,
            Suppression.channel == "email",
            Suppression.address_normalized == email.strip().lower(),
        )
    )


def contact_check(
    db: Session, lead: Lead, now: datetime | None = None, ignore_cooldown: bool = False
) -> list[dict]:
    """Every rule with its outcome. A lead may be contacted only if all pass (§8.5)."""
    now = now or datetime.now(UTC)
    org = db.get(Organization, lead.organization_id)
    cfg = _org_settings(org)
    max_attempts = int(cfg.get("max_attempts", MAX_ATTEMPTS))
    cooldown = int(cfg.get("cooldown_days", COOLDOWN_DAYS))
    stage = db.get(PipelineStage, lead.stage_id) if lead.stage_id else None
    outbound = db.execute(
        select(func.count(), func.max(CommunicationLog.occurred_at)).where(
            CommunicationLog.lead_id == lead.id,
            CommunicationLog.direction == "out",
            CommunicationLog.status == "sent",
        )
    ).one()
    sent_count, last_out = outbound
    replied = db.scalar(
        select(func.count())
        .select_from(CommunicationLog)
        .where(CommunicationLog.lead_id == lead.id, CommunicationLog.direction == "in")
    )
    suppressed = is_suppressed(db, lead.organization_id, lead.email)
    days = (now - last_out).days if last_out else None
    checks = [
        ("open", "Lead is in an open stage", stage is None or stage.category == "open"),
        ("not_replied", "No reply from the customer logged", not replied),
        ("contactable", "Not marked do not contact", not lead.do_not_contact),
        (
            "not_suppressed",
            "Address not on the suppression list" + (f" ({suppressed})" if suppressed else ""),
            suppressed is None,
        ),
        ("email", "Has an email address", bool(lead.email)),
        (
            "attempts",
            f"Fewer than {max_attempts} emails sent ({sent_count})",
            sent_count < max_attempts,
        ),
    ]
    if not ignore_cooldown:
        checks.append(
            (
                "cooldown",
                f"At least {cooldown} days since the last email"
                + (f" ({days} days)" if days is not None else ""),
                days is None or days >= cooldown,
            )
        )
    return [{"key": k, "label": label, "ok": bool(ok)} for k, label, ok in checks]


def allowed(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks)


def failed_reason(checks: list[dict]) -> str:
    return "; ".join(c["label"] for c in checks if not c["ok"])[:200]


def suppress(
    db: Session, org_id: uuid.UUID, email: str, reason: str, actor_id: uuid.UUID | None
) -> None:
    db.execute(
        insert(Suppression)
        .values(
            organization_id=org_id,
            channel="email",
            address_normalized=email.strip().lower(),
            reason=reason,
            created_by=actor_id,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "channel", "address_normalized"])
    )


def _cancel_open(db: Session, lead: Lead, reason: str) -> int:
    n = (
        db.execute(
            update(FollowUp)
            .where(
                FollowUp.lead_id == lead.id, FollowUp.status.in_(("scheduled", "awaiting_approval"))
            )
            .values(status="cancelled", skip_reason=reason)
        ).rowcount
        or 0
    )
    db.execute(
        update(CommunicationDraft)
        .where(
            CommunicationDraft.lead_id == lead.id,
            CommunicationDraft.status.in_(("draft", "pending_approval", "approved")),
        )
        .values(status="cancelled")
    )
    lead.next_follow_up_at = None
    return n


def mark_replied(
    db: Session, lead: Lead, actor_id: uuid.UUID | None, note: str | None = None
) -> None:
    """The customer answered: log it, stop all automatic follow-ups for this lead."""
    now = datetime.now(UTC)
    db.add(
        CommunicationLog(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            direction="in",
            channel="email",
            status="replied",
            error=(note or None) and note[:300],
            occurred_at=now,
        )
    )
    lead.last_interaction_at = now
    cancelled = _cancel_open(db, lead, "customer replied")
    record(
        db,
        lead.organization_id,
        lead.id,
        "reply_logged",
        "user",
        actor_id,
        cancelled_follow_ups=cancelled,
    )


def opt_out(db: Session, lead: Lead, actor_id: uuid.UUID | None) -> None:
    """The customer asked not to be contacted: suppress the address everywhere."""
    if lead.email:
        suppress(db, lead.organization_id, lead.email, "unsubscribed", actor_id)
    lead.do_not_contact = True
    cancelled = _cancel_open(db, lead, "opted out")
    record(
        db,
        lead.organization_id,
        lead.id,
        "opted_out",
        "user",
        actor_id,
        cancelled_follow_ups=cancelled,
    )


def schedule(
    db: Session,
    lead: Lead,
    due_at: datetime,
    actor_id: uuid.UUID | None,
    attempt_no: int | None = None,
) -> FollowUp:
    """Manual (or automatic) follow-up. Only one open follow-up per lead."""
    db.execute(
        update(FollowUp)
        .where(FollowUp.lead_id == lead.id, FollowUp.status == "scheduled")
        .values(status="cancelled", skip_reason="replaced by a new schedule")
    )
    sent = (
        db.scalar(
            select(func.count())
            .select_from(CommunicationLog)
            .where(
                CommunicationLog.lead_id == lead.id,
                CommunicationLog.direction == "out",
                CommunicationLog.status == "sent",
            )
        )
        or 0
    )
    fu = FollowUp(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        due_at=due_at,
        status="scheduled",
        attempt_no=attempt_no or sent + 1,
        assigned_to=lead.assigned_to,
    )
    db.add(fu)
    lead.next_follow_up_at = due_at
    db.flush()
    record(
        db,
        lead.organization_id,
        lead.id,
        "follow_up_scheduled",
        "user" if actor_id else "system",
        actor_id,
        due_at=due_at.isoformat(),
    )
    return fu


# ---------------------------------------------------------------- W5: due follow-ups


def in_business_hours(org: Organization, now: datetime) -> bool:
    """Contact only inside the organization's own working hours, in its own timezone."""
    try:
        local = now.astimezone(ZoneInfo(org.timezone or "UTC"))
    except Exception:  # noqa: BLE001 - unknown zone name: fall back to UTC
        local = now.astimezone(UTC)
    return local.weekday() < 5 and BUSINESS_START <= local.time() < BUSINESS_END


def due_follow_ups(
    db: Session, now: datetime | None = None, limit: int = 100, org_id: uuid.UUID | None = None
) -> list[FollowUp]:
    now = now or datetime.now(UTC)
    stmt = (
        select(FollowUp)
        .where(FollowUp.status == "scheduled", FollowUp.due_at <= now)
        .order_by(FollowUp.due_at)
        .limit(limit)
    )
    if org_id:
        stmt = stmt.where(FollowUp.organization_id == org_id)
    items = db.scalars(stmt).all()
    orgs: dict[uuid.UUID, bool] = {}
    out = []
    for fu in items:
        if fu.organization_id not in orgs:
            orgs[fu.organization_id] = in_business_hours(
                db.get(Organization, fu.organization_id), now
            )
        if orgs[fu.organization_id]:
            out.append(fu)
    return out


def prepare(db: Session, fu: FollowUp, now: datetime | None = None) -> dict:
    """Check the rules; skip with a reason, or write a follow-up draft for approval. Never
    sends. Idempotent: only a `scheduled` follow-up is prepared."""
    from app.services import approvals, drafting

    if fu.status != "scheduled":
        return {"status": fu.status, "skipped": "already handled"}
    lead = db.get(Lead, fu.lead_id)
    checks = contact_check(db, lead, now)
    if not allowed(checks):
        fu.status, fu.skip_reason = "skipped", failed_reason(checks)
        fu.completed_at = now or datetime.now(UTC)
        lead.next_follow_up_at = None
        record(
            db,
            fu.organization_id,
            lead.id,
            "follow_up_skipped",
            "system",
            None,
            reason=fu.skip_reason,
        )
        db.commit()
        return {"status": "skipped", "reason": fu.skip_reason}
    org = db.get(Organization, fu.organization_id)
    style = (org.settings or {}).get("ai", {}).get("default_style", "professional")
    try:
        d = drafting.generate_draft(db, org.id, lead.id, style, kind="follow_up")
    except drafting.DraftRefused as exc:
        fu.status, fu.skip_reason = "skipped", str(exc)[:200]
        db.commit()
        return {"status": "skipped", "reason": fu.skip_reason}
    draft = approvals.save_generated(db, org.id, lead, d, None)
    fu.status, fu.draft_id = "awaiting_approval", draft.id
    db.commit()
    return {
        "status": "awaiting_approval",
        "draft_id": str(draft.id),
        "assigned_to": str(fu.assigned_to) if fu.assigned_to else None,
    }


def on_sent(db: Session, draft: CommunicationDraft, now: datetime) -> None:
    """After any email is sent: close the follow-up it answered, schedule the next one if the
    rules still allow another attempt (checked again when it falls due)."""
    db.execute(
        update(FollowUp)
        .where(FollowUp.draft_id == draft.id)
        .values(status="done", completed_at=now)
    )
    lead = db.get(Lead, draft.lead_id)
    org = db.get(Organization, draft.organization_id)
    cfg = _org_settings(org)
    days = int(cfg.get("cooldown_days", COOLDOWN_DAYS))
    # Cooldown is applied by the due date itself; the other rules are checked now and again
    # when the follow-up falls due.
    if allowed(contact_check(db, lead, now, ignore_cooldown=True)):
        schedule(db, lead, now + timedelta(days=days), None)
    else:
        lead.next_follow_up_at = None


# ---------------------------------------------------------------- W6: recovery


def recovery_candidates(
    db: Session, org_id: uuid.UUID, now: datetime | None = None, limit: int = 20
) -> list[Lead]:
    """Open leads with no activity for 14+ days, contactable, not recovered in the last 30."""
    now = now or datetime.now(UTC)
    quiet = now - timedelta(days=RECOVERY_AFTER_DAYS)
    recent_recovery = now - timedelta(days=RECOVERY_COOLDOWN_DAYS)
    recovered = select(CommunicationDraft.lead_id).where(
        CommunicationDraft.kind == "recovery", CommunicationDraft.created_at >= recent_recovery
    )
    rows = db.scalars(
        select(Lead)
        .join(PipelineStage, PipelineStage.id == Lead.stage_id)
        .where(
            Lead.organization_id == org_id,
            Lead.archived_at.is_(None),
            Lead.do_not_contact.is_(False),
            Lead.email.is_not(None),
            PipelineStage.category == "open",
            Lead.last_interaction_at < quiet,
            Lead.id.not_in(recovered),
        )
        .order_by(Lead.score.desc().nulls_last())
        .limit(limit * 2)
    ).all()
    return [x for x in rows if allowed(contact_check(db, x, now, ignore_cooldown=True))][:limit]


def recovery_reason(db: Session, lead: Lead, now: datetime | None = None) -> str:
    """From stored records only (§8.5); never a guess."""
    now = now or datetime.now(UTC)
    stage = db.get(PipelineStage, lead.stage_id) if lead.stage_id else None
    days = (now - lead.last_interaction_at).days
    loss = (lead.custom_fields or {}).get("loss_reason")
    parts = [f"No activity for {days} days", f"last stage: {stage.label if stage else 'unknown'}"]
    parts.append(f"recorded reason: {loss}" if loss else "reason unknown")
    return "; ".join(parts)


def recovery_suggestion(db: Session, lead: Lead, now: datetime | None = None) -> dict:
    from app.services import approvals, drafting

    if not allowed(contact_check(db, lead, now, ignore_cooldown=True)):
        return {"skipped": "lead cannot be contacted"}
    # Idempotent: a retried call returns the open recovery draft instead of writing another.
    existing = db.scalar(
        select(CommunicationDraft).where(
            CommunicationDraft.lead_id == lead.id,
            CommunicationDraft.kind == "recovery",
            CommunicationDraft.status == "pending_approval",
        )
    )
    if existing is not None:
        return {
            "draft_id": str(existing.id),
            "reason": recovery_reason(db, lead, now),
            "already": True,
        }
    org = db.get(Organization, lead.organization_id)
    style = (org.settings or {}).get("ai", {}).get("default_style", "professional")
    try:
        d = drafting.generate_draft(db, org.id, lead.id, style, kind="recovery")
    except drafting.DraftRefused as exc:
        return {"skipped": str(exc)}
    draft = approvals.save_generated(db, org.id, lead, d, None)
    reason = recovery_reason(db, lead, now)
    record(db, org.id, lead.id, "recovery_suggested", "system", None, reason=reason)
    db.commit()
    return {"draft_id": str(draft.id), "reason": reason}
