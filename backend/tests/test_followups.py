"""P8 gate: no contact for replied / opted-out / do-not-contact / max-attempts / cooldown;
schedules fire at the right local hour; merge only by a person; the sweeper recovers events."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select

from app.models import (
    CommunicationDraft,
    CommunicationLog,
    DuplicateCandidate,
    FollowUp,
    Lead,
    Organization,
    OutboxEvent,
)
from app.services import followups, outbox
from tests.test_approvals import MSG, _service_key_for, queued, svc
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse


def _lead(db, lead_json) -> Lead:
    return db.get(Lead, uuid.UUID(lead_json["id"]))


def _sent(db, lead: Lead, days_ago: float) -> None:
    db.add(
        CommunicationLog(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            direction="out",
            channel="email",
            status="sent",
            occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    db.flush()


def _due_fu(db, lead: Lead) -> FollowUp:
    f = followups.schedule(db, lead, datetime.now(UTC) - timedelta(minutes=1), None)
    db.flush()
    return f


def test_follow_up_prepared_when_rules_pass(client, db, owner):  # noqa: F811
    lead = _lead(db, new_lead(client, message=MSG))
    client.post(f"/api/v1/leads/{lead.id}/reanalyze")
    _sent(db, lead, 4)
    r = followups.prepare(db, _due_fu(db, lead))
    assert r["status"] == "awaiting_approval"
    d = db.get(CommunicationDraft, uuid.UUID(r["draft_id"]))
    assert d.kind == "follow_up" and d.status == "pending_approval"


def _skip_reason(db, lead) -> str:
    r = followups.prepare(db, _due_fu(db, lead))
    assert r["status"] == "skipped", r
    return r["reason"]


def test_no_contact_after_reply(client, db, owner):  # noqa: F811
    lead = _lead(db, new_lead(client, message=MSG))
    _sent(db, lead, 4)
    followups.mark_replied(db, lead, None)
    assert "No reply from the customer" in _skip_reason(db, lead)


def test_no_contact_after_opt_out_and_suppression_blocks_every_path(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    lead_json, d = queued(client)
    lead = _lead(db, lead_json)
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    # Opted out after approval: the send claim refuses and cancels the draft.
    followups.suppress(db, lead.organization_id, lead.email, "unsubscribed", None)
    db.flush()
    r = client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key))
    assert r.status_code == 409
    assert db.get(CommunicationDraft, uuid.UUID(d["id"])).status == "cancelled"
    # And new drafts cannot be approved.
    d2 = client.post(f"/api/v1/leads/{lead.id}/drafts", json={}).json()
    assert client.post(f"/api/v1/drafts/{d2['id']}/approve").status_code == 409
    _sent(db, lead, 4)
    assert "suppression list" in _skip_reason(db, lead)


def test_opt_out_endpoint_cancels_everything(client, db, owner):  # noqa: F811
    lead_json, d = queued(client)
    lead = _lead(db, lead_json)
    _due_fu(db, lead)
    assert client.post(f"/api/v1/leads/{lead.id}/opt-out").json() == {"ok": True}
    assert db.get(CommunicationDraft, uuid.UUID(d["id"])).status == "cancelled"
    assert db.scalar(select(FollowUp.status).where(FollowUp.lead_id == lead.id)) == "cancelled"
    assert db.get(Lead, lead.id).do_not_contact is True


def test_no_contact_when_do_not_contact(client, db, owner):  # noqa: F811
    lead = _lead(db, new_lead(client, message=MSG))
    _sent(db, lead, 4)
    lead.do_not_contact = True
    db.flush()
    assert "do not contact" in _skip_reason(db, lead)


def test_no_contact_after_max_attempts(client, db, owner):  # noqa: F811
    lead = _lead(db, new_lead(client, message=MSG))
    for days in (12, 8, 4):
        _sent(db, lead, days)
    assert "Fewer than 3 emails sent (3)" in _skip_reason(db, lead)


def test_no_contact_inside_cooldown(client, db, owner):  # noqa: F811
    lead = _lead(db, new_lead(client, message=MSG))
    _sent(db, lead, 1)
    assert "At least 3 days" in _skip_reason(db, lead)


def test_closed_stage_blocks_contact(client, db, owner):  # noqa: F811
    from app.models import PipelineStage

    lead = _lead(db, new_lead(client, message=MSG))
    lead.stage_id = db.scalar(
        select(PipelineStage.id).where(
            PipelineStage.organization_id == lead.organization_id, PipelineStage.key == "won"
        )
    )
    _sent(db, lead, 4)
    assert "open stage" in _skip_reason(db, lead)


def test_sent_email_schedules_next_until_max(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    lead_json, d = queued(client)
    lead = _lead(db, lead_json)
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key))
    client.post(f"/api/v1/internal/drafts/{d['id']}/mark-sent", json={}, headers=svc(key))
    fu = db.scalar(
        select(FollowUp).where(FollowUp.lead_id == lead.id, FollowUp.status == "scheduled")
    )
    assert fu is not None and fu.attempt_no == 2
    for days in (9, 6):
        _sent(db, lead, days)  # now 3 sent in total
    approvals_draft = CommunicationDraft(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        subject="s",
        body="b",
        style="professional",
        source="template",
        status="sent",
    )
    db.add(approvals_draft)
    db.flush()
    followups.on_sent(db, approvals_draft, datetime.now(UTC))
    db.flush()
    scheduled = db.scalars(
        select(FollowUp).where(FollowUp.lead_id == lead.id, FollowUp.status == "scheduled")
    ).all()
    assert len(scheduled) <= 1 and db.get(Lead, lead.id).next_follow_up_at is None


def test_due_follow_ups_respect_local_business_hours(client, db, owner):  # noqa: F811
    lead = _lead(db, new_lead(client, message=MSG))
    org = db.get(Organization, lead.organization_id)
    org.timezone = "Asia/Karachi"  # UTC+5
    f = followups.schedule(db, lead, datetime(2026, 11, 23, 0, 0, tzinfo=UTC), None)
    db.flush()

    def due_at(utc_hour: int, day: int = 24) -> bool:
        now = datetime(2026, 11, day, utc_hour, 30, tzinfo=UTC)
        return f in followups.due_follow_ups(db, now, org_id=org.id)

    assert not due_at(3)  # 08:30 in Karachi, before opening
    assert due_at(4)  # 09:30 in Karachi
    assert due_at(11)  # 16:30
    assert not due_at(12)  # 17:30, closed
    assert not due_at(6, day=28)  # Saturday
    org.timezone = "America/Los_Angeles"  # UTC-8 in November
    db.flush()
    assert not due_at(12)  # 04:30 in Los Angeles
    assert due_at(17)  # 09:30 in Los Angeles


def test_internal_due_and_prepare(client, db, owner, monkeypatch):  # noqa: F811
    key = _service_key_for(db, owner)
    lead = _lead(db, new_lead(client, message=MSG))
    client.post(f"/api/v1/leads/{lead.id}/reanalyze")
    _sent(db, lead, 4)
    f = _due_fu(db, lead)
    monkeypatch.setattr(followups, "in_business_hours", lambda org, now: True)
    due = client.get("/api/v1/internal/follow-ups/due", headers=svc(key)).json()["items"]
    assert [x["id"] for x in due] == [str(f.id)]
    first = client.post(f"/api/v1/internal/follow-ups/{f.id}/prepare", headers=svc(key)).json()
    again = client.post(f"/api/v1/internal/follow-ups/{f.id}/prepare", headers=svc(key)).json()
    assert first["status"] == "awaiting_approval" and again["skipped"] == "already handled"


def test_duplicate_scan_never_merges_and_preview_changes_nothing(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    new_lead(client, full_name="Amira Hassan", email="a1@example.com", company="Cedar Bakery")
    new_lead(client, full_name="Amira Hasan", email="a2@example.com", company="Cedar Bakery")
    r = client.post("/api/v1/internal/duplicates/scan", headers=svc(key)).json()
    assert r["added"] == 1 and r["notify"] and "Nothing was merged" in r["text"]
    cand = db.scalar(select(DuplicateCandidate))
    p = client.get(f"/api/v1/duplicates/{cand.id}/preview", params={"keep": str(cand.lead_a_id)})
    assert p.status_code == 200 and {f["field"] for f in p.json()["fields"]} >= {"email", "company"}
    assert (
        db.scalar(select(func.count()).select_from(Lead).where(Lead.archived_at.is_not(None))) == 0
    )
    assert db.get(DuplicateCandidate, cand.id).status == "open"


def test_sweeper_recovers_stalled_outbox_events(db, org):
    ev = OutboxEvent(
        organization_id=org.id,
        event_type="lead.created",
        status="failed",
        attempts=8,
        payload={"event": "lead.created", "event_id": "x", "data": {}},
    )
    db.add(ev)
    db.flush()
    assert outbox.redispatch_failed(db) >= 1
    db.refresh(ev)
    assert ev.status == "pending" and ev.attempts == 0
    from app.core.config import get_settings

    ok = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200)))
    outbox.dispatch_once(db, get_settings(), ok)
    db.refresh(ev)
    assert ev.status == "delivered"


def test_mark_replied_endpoint_and_contact_rules(client, db, owner):  # noqa: F811
    lead_json, d = queued(client)
    assert client.post(
        f"/api/v1/leads/{lead_json['id']}/replied", json={"note": "Called back"}
    ).json()
    rules = client.get(f"/api/v1/leads/{lead_json['id']}/contact-rules").json()
    assert rules["allowed"] is False
    assert any(c["key"] == "not_replied" and not c["ok"] for c in rules["checks"])
    assert db.get(CommunicationDraft, uuid.UUID(d["id"])).status == "cancelled"
