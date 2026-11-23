"""P6 slice 1: draft lifecycle, approval, the atomic send claim, basic follow-up scheduling."""

import re
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.models import AuditLog, CommunicationLog, FollowUp, Lead, OutboxEvent
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse

MSG = (
    "We run a bakery and need a new website with online ordering. Budget around $2,000, "
    "live within a month. Can you send a quote?"
)


def queued(client, **kw):
    lead = new_lead(client, message=MSG, **kw)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    r = client.post(f"/api/v1/leads/{lead['id']}/drafts", json={})
    assert r.status_code == 201, r.text
    return lead, r.json()


def svc(service_key):
    return {"X-Service-Key": service_key}


def test_draft_enters_queue_pending_with_lead_recipient(client, owner):  # noqa: F811
    lead, d = queued(client)
    assert d["status"] == "pending_approval" and d["to"] == "amira@example.com"
    queue = client.get("/api/v1/drafts").json()
    assert [x["id"] for x in queue] == [d["id"]] and queue[0]["lead_name"] == "Amira Hassan"


def test_new_draft_cancels_the_previous_open_one(client, owner):  # noqa: F811
    lead, first = queued(client)
    second = client.post(f"/api/v1/leads/{lead['id']}/drafts", json={}).json()
    assert client.get(f"/api/v1/drafts/{first['id']}").json()["status"] == "cancelled"
    assert [x["id"] for x in client.get("/api/v1/drafts").json()] == [second["id"]]


def test_edit_reruns_checks_and_blocks_approval(client, owner):  # noqa: F811
    _, d = queued(client)
    bad = client.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"subject": "Hi", "body": "Special 50% discount, only $99!"},
    ).json()
    assert bad["edited"] and not bad["all_passed"]
    r = client.post(f"/api/v1/drafts/{d['id']}/approve")
    assert r.status_code == 409 and "Fix these checks" in r.text
    assert client.get(f"/api/v1/drafts/{d['id']}").json()["status"] == "pending_approval"


def test_approve_emits_event_and_audit(client, db, owner):  # noqa: F811
    _, d = queued(client)
    r = client.post(f"/api/v1/drafts/{d['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    ev = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "draft.approved")).all()
    assert len(ev) == 1 and ev[0].payload["data"]["draft_id"] == d["id"]
    assert (
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "draft.approved")
        )
        == 1
    )
    # Approving twice is refused.
    assert client.post(f"/api/v1/drafts/{d['id']}/approve").status_code == 409


def test_do_not_contact_blocks_approval(client, db, owner):  # noqa: F811
    lead, d = queued(client)
    db.get(Lead, uuid.UUID(lead["id"])).do_not_contact = True
    db.flush()
    assert client.post(f"/api/v1/drafts/{d['id']}/approve").status_code == 409


def test_reject_needs_a_reason(client, owner):  # noqa: F811
    _, d = queued(client)
    assert client.post(f"/api/v1/drafts/{d['id']}/reject", json={"reason": ""}).status_code == 422
    r = client.post(f"/api/v1/drafts/{d['id']}/reject", json={"reason": "Wrong tone"})
    assert r.json()["status"] == "rejected" and r.json()["rejection_reason"] == "Wrong tone"


def _service_key_for(db, owner_body):
    from app.core.security import hash_key, key_prefix
    from app.models import ApiKey

    key = f"svc_{uuid.uuid4().hex}"
    db.add(
        ApiKey(
            organization_id=uuid.UUID(owner_body["organization_id"]),
            name="t",
            prefix=key_prefix(key),
            key_hash=hash_key(key),
            scopes=["internal"],
        )
    )
    db.flush()
    return key


def test_no_send_unless_approved(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    _, d = queued(client)
    # Pending: the send claim is refused.
    url = f"/api/v1/internal/drafts/{d['id']}/claim-send"
    assert client.post(url, headers=svc(key)).status_code == 409
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    first = client.post(url, headers=svc(key))
    assert first.status_code == 200 and first.json()["to"] == "amira@example.com"
    # A redelivered event cannot claim it again.
    assert client.post(url, headers=svc(key)).status_code == 409


def test_mark_sent_logs_and_schedules_follow_up(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    lead, d = queued(client)
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key))
    r = client.post(
        f"/api/v1/internal/drafts/{d['id']}/mark-sent",
        json={"provider_message_id": "<abc@mailpit>"},
        headers=svc(key),
    )
    assert r.json()["status"] == "sent"
    log = db.scalar(select(CommunicationLog))
    assert log.provider_message_id == "<abc@mailpit>" and log.direction == "out"
    fu = db.scalar(select(FollowUp))
    assert fu.status == "scheduled" and (fu.due_at - log.occurred_at).days == 3
    # Marking sent again is refused (not in "sending").
    again = client.post(f"/api/v1/internal/drafts/{d['id']}/mark-sent", json={}, headers=svc(key))
    assert again.status_code == 409


def test_mark_failed(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    _, d = queued(client)
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key))
    r = client.post(
        f"/api/v1/internal/drafts/{d['id']}/mark-failed",
        json={"error": "SMTP 550 refused"},
        headers=svc(key),
    )
    assert r.json()["status"] == "failed"
    assert client.get(f"/api/v1/drafts/{d['id']}").json()["send_error"] == "SMTP 550 refused"


def test_internal_generate_is_idempotent(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    lead = new_lead(client, message=MSG)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    url = f"/api/v1/internal/leads/{lead['id']}/drafts/generate"
    h = {**svc(key), "Idempotency-Key": "evt-1:draft"}
    first = client.post(url, headers=h).json()
    second = client.post(url, headers=h).json()
    assert first["first_delivery"] and first["draft_id"]
    assert second == {"first_delivery": False, "skipped": "already handled"}
    assert len(client.get("/api/v1/drafts").json()) == 1


def test_another_orgs_draft_is_404(client, db, owner):  # noqa: F811
    from app.models import CommunicationDraft, Organization

    other = Organization(name="O", slug="o-dr", public_form_key="pk_dr")
    db.add(other)
    db.flush()
    lead = Lead(organization_id=other.id, full_name="X", email="x@example.com")
    db.add(lead)
    db.flush()
    d = CommunicationDraft(
        organization_id=other.id,
        lead_id=lead.id,
        subject="s",
        body="b",
        style="professional",
        source="template",
    )
    db.add(d)
    db.flush()
    assert client.get(f"/api/v1/drafts/{d.id}").status_code == 404
    assert client.post(f"/api/v1/drafts/{d.id}/approve").status_code == 404


def test_only_claim_send_moves_a_draft_to_sending():
    """Static guard: the string "sending" is written in exactly one place, the atomic claim
    that requires status == "approved"."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    writers = []
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'status\s*=\s*"sending"|\.values\(status="sending"\)', text):
            writers.append((path.name, text[max(0, m.start() - 400) : m.start()]))
    assert len(writers) == 1, writers
    name, before = writers[0]
    assert name == "approvals.py" and 'CommunicationDraft.status == "approved"' in before


def test_workflow_error_alerts_are_throttled(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    body = {
        "workflow_key": "W4b",
        "n8n_execution_id": "1",
        "last_node": "Send email",
        "message": "SMTP refused",
    }
    first = client.post("/api/v1/internal/workflow-errors", json=body, headers=svc(key)).json()
    second = client.post(
        "/api/v1/internal/workflow-errors", json={**body, "n8n_execution_id": "2"}, headers=svc(key)
    ).json()
    other = client.post(
        "/api/v1/internal/workflow-errors",
        json={**body, "workflow_key": "W1", "n8n_execution_id": "3"},
        headers=svc(key),
    ).json()
    assert first["should_alert"] and not second["should_alert"] and other["should_alert"]
    assert "Leads are safe" in first["text"]


def test_failed_telegram_alert_notifies_admin_and_leaves_lead_alone(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    lead = new_lead(client, message=MSG)
    before = client.get(f"/api/v1/leads/{lead['id']}").json()
    body = {
        "lead_id": lead["id"],
        "channel": "telegram",
        "status": "failed",
        "error": "connect ETIMEDOUT api.telegram.org",
        "n8n_execution_id": "77",
    }
    r = client.post("/api/v1/internal/notifications/log", json=body, headers=svc(key)).json()
    assert r["should_alert"] is True and "telegram" in r["subject"].lower()
    after = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert {k: after[k] for k in ("score", "priority", "stage")} == {
        k: before[k] for k in ("score", "priority", "stage")
    }
    timeline = client.get(f"/api/v1/leads/{lead['id']}/activities").json()
    assert any(a["type"] == "alert_failed" for a in timeline)
    ok = client.post(
        "/api/v1/internal/notifications/log",
        json={**body, "status": "sent", "error": None},
        headers=svc(key),
    ).json()
    assert ok == {"should_alert": False}


def test_contract_fixtures_match_the_real_shapes(client, db, owner):  # noqa: F811
    import json as _json

    from app.services.leads import _event_envelope

    folder = Path(__file__).resolve().parents[2] / "contracts" / "internal-api"
    fx = {p.name: _json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")}
    real = _event_envelope("draft.approved", uuid.uuid4(), {"draft_id": "x", "lead_id": "y"})
    assert set(real) == set(fx["event-draft-approved.json"])
    assert set(real["data"]) == set(fx["event-draft-approved.json"]["data"])
    key = _service_key_for(db, owner)
    _, d = queued(client)
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    claim = client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key)).json()
    assert set(claim) == set(fx["response-claim-send-200.json"])
    again = client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key)).json()
    assert set(again["error"]) >= {"code", "message"}
