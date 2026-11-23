"""Phase 3: intake, dedupe, idempotency, internal API auth, fake analysis, run logging, outbox."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select

from app.models import (
    Lead,
    LeadInquiry,
    Organization,
    OutboxEvent,
    Service,
    WorkflowExecution,
)
from app.services import outbox

FORM = {
    "full_name": "Amira Hassan",
    "email": "Amira@Example.com ",
    "company": "Cedar & Pine Bakery",
    "service": "Website Development",
    "budget": "$1,500 to $5,000",
    "timeline": "Within 1 month",
    "message": "We need a new website with online ordering. Budget around $2,000. Quote please?",
    "consent": True,
}


def post_lead(client, org, body=None, **headers):
    return client.post(
        "/api/v1/public/leads",
        json=body or FORM,
        headers={"X-Form-Key": org.public_form_key, **headers},
    )


def count(db, model, org):
    return db.scalar(select(func.count()).select_from(model).where(model.organization_id == org.id))


# ---------- public intake ----------


def test_new_lead_creates_lead_inquiry_and_outbox_event(client, db, org):
    resp = post_lead(client, org)
    assert resp.status_code == 201
    assert resp.json()["status"] == "received"
    lead = db.scalar(select(Lead).where(Lead.organization_id == org.id))
    assert lead.email_normalized == "amira@example.com"
    assert lead.ai_status == "pending"
    assert count(db, LeadInquiry, org) == 1
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.organization_id == org.id))
    assert event.event_type == "lead.created"
    assert event.payload["data"]["lead_id"] == str(lead.id)
    assert event.payload["request_id"]  # correlation id travels with the event


def test_same_submission_twice_creates_nothing_new(client, db, org):
    first = post_lead(client, org)
    second = post_lead(client, org)
    assert first.json()["reference"] == second.json()["reference"]
    assert count(db, Lead, org) == 1
    assert count(db, LeadInquiry, org) == 1
    assert count(db, OutboxEvent, org) == 1


def test_returning_email_adds_inquiry_not_duplicate_lead(client, db, org):
    post_lead(client, org)
    post_lead(client, org, {**FORM, "email": "amira@example.com", "message": "One more question."})
    assert count(db, Lead, org) == 1
    assert count(db, LeadInquiry, org) == 2
    assert count(db, OutboxEvent, org) == 2


def test_honeypot_looks_like_success_but_stores_nothing(client, db, org):
    resp = post_lead(client, org, {**FORM, "nickname": "bot"})
    assert resp.status_code == 201
    assert count(db, Lead, org) == 0


def test_unknown_form_key_is_rejected(client, db, org):
    resp = client.post("/api/v1/public/leads", json=FORM, headers={"X-Form-Key": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_validation_errors_use_envelope_and_do_not_echo_values(client, org):
    resp = post_lead(client, org, {**FORM, "consent": False, "email": "not-an-email"})
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "validation_error"
    fields = {d["field"] for d in body["details"]}
    assert {"consent", "email"} <= fields
    assert "not-an-email" not in resp.text


def test_rate_limit_blocks_the_eleventh_request_per_minute(client, org):
    for i in range(10):
        assert post_lead(client, org, {**FORM, "message": f"msg {i}"}).status_code == 201
    assert post_lead(client, org, {**FORM, "message": "msg 11"}).status_code == 429


# ---------- internal API (n8n) ----------


def _lead_id(client, db, org):
    post_lead(client, org)
    return db.scalar(select(Lead.id).where(Lead.organization_id == org.id))


def test_internal_requires_a_valid_service_key(client, db, org, service_key):
    lead_id = _lead_id(client, db, org)
    url = f"/api/v1/internal/leads/{lead_id}/analyze"
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"X-Service-Key": "wrong"}).status_code == 401
    assert client.post(url, headers={"X-Service-Key": service_key}).status_code == 200


def test_service_key_cannot_reach_another_organizations_lead(client, db, org, service_key):
    other = Organization(name="Other", slug=f"o-{uuid.uuid4().hex[:6]}", public_form_key="pk_o")
    db.add(other)
    db.flush()
    lead = Lead(organization_id=other.id, full_name="X", email="x@example.com")
    db.add(lead)
    db.flush()
    resp = client.post(
        f"/api/v1/internal/leads/{lead.id}/analyze", headers={"X-Service-Key": service_key}
    )
    assert resp.status_code == 404


def test_fake_analysis_scores_and_is_idempotent(client, db, org, service_key):
    db.add(
        Service(
            organization_id=org.id,
            name="Website Development",
            keywords=["website"],
            price_min_minor=150000,
            price_max_minor=500000,
        )
    )
    db.flush()
    lead_id = _lead_id(client, db, org)
    headers = {"X-Service-Key": service_key}
    first = client.post(f"/api/v1/internal/leads/{lead_id}/analyze", headers=headers).json()
    second = client.post(f"/api/v1/internal/leads/{lead_id}/analyze", headers=headers).json()
    assert first["ai_status"] == "done"
    assert first["score_source"] == "fake"
    assert first["band"] == "high"  # budget + intent + timeline + service + company
    assert second["score"] == first["score"]


def test_alert_summary_is_plain_text_with_link_in_text(client, db, org, service_key):
    lead_id = _lead_id(client, db, org)
    headers = {"X-Service-Key": service_key}
    client.post(f"/api/v1/internal/leads/{lead_id}/analyze", headers=headers)
    body = client.get(f"/api/v1/internal/leads/{lead_id}/alert-summary", headers=headers).json()
    assert "Amira Hassan" in body["title"]
    assert body["link"] in body["text"]


def test_workflow_run_upsert_never_duplicates(client, db, org, service_key):
    lead_id = _lead_id(client, db, org)
    headers = {"X-Service-Key": service_key}
    run = {
        "workflow_key": "W1",
        "n8n_execution_id": "123",
        "status": "running",
        "lead_id": str(lead_id),
    }
    client.post("/api/v1/internal/workflow-runs", json=run, headers=headers)
    client.post(
        "/api/v1/internal/workflow-runs", json={**run, "status": "success"}, headers=headers
    )
    rows = db.scalars(
        select(WorkflowExecution).where(WorkflowExecution.organization_id == org.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].status == "success"


# ---------- outbox dispatcher ----------


def _settings():
    from app.core.config import Settings

    return Settings(n8n_webhook_secret="s3cret", outbox_max_attempts=3)


def _event(db, org):
    ev = OutboxEvent(
        organization_id=org.id,
        event_type="lead.created",
        payload={
            "event": "lead.created",
            "event_id": str(uuid.uuid4()),
            "request_id": "r1",
            "data": {},
        },
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db.add(ev)
    db.flush()
    return ev


def test_outbox_delivers_with_secret_and_idempotency_headers(db, org):
    ev = _event(db, org)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["secret"] = request.headers["X-Webhook-Secret"]
        seen["idem"] = request.headers["Idempotency-Key"]
        seen["path"] = request.url.path
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert outbox.dispatch_once(db, _settings(), http) == 1
    assert ev.status == "delivered"
    assert seen == {
        "secret": "s3cret",
        "idem": ev.payload["event_id"],
        "path": "/webhook/rl/lead-created",
    }


def test_outbox_retries_with_backoff_then_fails_after_max_attempts(db, org):
    ev = _event(db, org)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
        outbox.dispatch_once(db, _settings(), http)
        assert ev.status == "pending" and ev.attempts == 1
        assert ev.next_attempt_at > datetime.now(UTC)  # backed off, not retried at once
        for _ in range(2):
            ev.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            outbox.dispatch_once(db, _settings(), http)
    assert ev.status == "failed"
    assert ev.last_error == "HTTP 503"
    assert outbox.redispatch_failed(db) >= 1
    db.refresh(ev)
    assert ev.status == "pending" and ev.attempts == 0


def test_outbox_survives_connection_errors(db, org):
    ev = _event(db, org)

    def down(request):
        raise httpx.ConnectError("n8n is down")

    with httpx.Client(transport=httpx.MockTransport(down)) as http:
        assert outbox.dispatch_once(db, _settings(), http) == 0
    assert ev.status == "pending"
    assert ev.last_error == "ConnectError"


def test_backoff_doubles_and_caps():
    assert [outbox.backoff_seconds(n) for n in (1, 2, 3)] == [15, 30, 60]
    assert outbox.backoff_seconds(20) == 600
