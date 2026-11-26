"""One n8n credential for every organization (backlog #38): a key with 'internal:any-org'
acts for the organization of the lead/draft/follow-up it names; a normal key stays scoped."""

import uuid

from app.core.security import hash_key
from app.models import (
    ApiKey,
    CommunicationDraft,
    Lead,
    LeadInquiry,
    Organization,
    WorkflowExecution,
)


def _org(db, name):
    o = Organization(
        name=name,
        slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        public_form_key=f"pk_{uuid.uuid4().hex}",
        settings={"services": ["Website Development"]},
    )
    db.add(o)
    db.flush()
    return o


def _key(db, org, scopes):
    raw = f"svc_{uuid.uuid4().hex}"
    db.add(
        ApiKey(
            organization_id=org.id, name="t", prefix=raw[:8], key_hash=hash_key(raw), scopes=scopes
        )
    )
    db.flush()
    return {"X-Service-Key": raw}


def _lead(db, org):
    lead = Lead(
        organization_id=org.id, full_name="Ana Example", email=f"{uuid.uuid4().hex[:6]}@example.com"
    )
    db.add(lead)
    db.flush()
    db.add(LeadInquiry(organization_id=org.id, lead_id=lead.id, message="Need a website, $3,000"))
    db.flush()
    return lead


def _approved_draft(db, org, lead):
    d = CommunicationDraft(
        organization_id=org.id,
        lead_id=lead.id,
        channel="email",
        kind="first_reply",
        to_address=lead.email,
        subject="Hello",
        body="Hi",
        status="approved",
        source="template",
        style="professional",
    )
    db.add(d)
    db.flush()
    return d


def test_any_org_key_claims_drafts_in_other_organizations(client, db, org):
    other = _org(db, "Other")
    draft = _approved_draft(db, other, _lead(db, other))
    scoped = _key(db, org, ["internal"])
    platform = _key(db, org, ["internal", "internal:any-org"])
    url = f"/api/v1/internal/drafts/{draft.id}/claim-send"
    assert client.post(url, headers=scoped).status_code in (404, 409)  # still org-scoped
    db.refresh(draft)
    assert draft.status == "approved"  # not claimed by another organization's key
    r = client.post(url, headers=platform)
    assert r.status_code == 200, r.text
    db.refresh(draft)
    assert draft.status == "sending"


def test_any_org_key_logs_runs_under_the_leads_organization(client, db, org):
    other = _org(db, "Other")
    lead = _lead(db, other)
    platform = _key(db, org, ["internal", "internal:any-org"])
    body = {
        "workflow_key": "W1",
        "n8n_execution_id": f"x-{uuid.uuid4().hex[:8]}",
        "status": "success",
        "lead_id": str(lead.id),
    }
    r = client.post("/api/v1/internal/workflow-runs", json=body, headers=platform)
    assert r.status_code == 200, r.text
    row = db.get(WorkflowExecution, uuid.UUID(r.json()["id"]))
    assert row.organization_id == other.id and row.lead_id == lead.id


def test_unknown_entity_is_404_for_the_any_org_key(client, db, org):
    platform = _key(db, org, ["internal", "internal:any-org"])
    r = client.post(f"/api/v1/internal/drafts/{uuid.uuid4()}/claim-send", headers=platform)
    assert r.status_code == 404


def test_scoped_key_still_cannot_reach_other_organizations_leads(client, db, org):
    other = _org(db, "Other")
    lead = _lead(db, other)
    scoped = _key(db, org, ["internal"])
    assert (
        client.get(f"/api/v1/internal/leads/{lead.id}/alert-summary", headers=scoped).status_code
        == 404
    )
