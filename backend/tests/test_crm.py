"""Phase 4 slice 3: leads CRUD, dedupe, search, filters, sorting, stage, assignment, archive,
erasure, notes, timeline, audit, role checks and cross-organization 404s."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    Lead,
    LeadActivity,
    LeadInquiry,
    OrganizationMember,
    OutboxEvent,
    User,
)
from app.services.auth import hash_password

PW = "Sunrise-Bakery-2026"  # fictional test-only password  # gitleaks:allow


@pytest.fixture
def owner(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Harbor Test",
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": PW,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def new_lead(client, **kw):
    body = {
        "full_name": "Amira Hassan",
        "email": "amira@example.com",
        "company": "Cedar & Pine Bakery",
        **kw,
    }
    resp = client.post("/api/v1/leads", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def stages(client):
    return {s["key"]: s["id"] for s in client.get("/api/v1/settings/pipeline").json()}


def test_create_lead_puts_it_on_new_with_manual_source(client, owner):
    lead = new_lead(client)
    assert lead["stage"]["key"] == "new"
    assert lead["source"] == "Added by hand"
    assert lead["ai_status"] == "skipped"  # no message, nothing to analyze
    assert lead["merged"] is False


def test_message_queues_analysis_through_the_outbox(client, db, owner):
    lead = new_lead(client, message="Need a website, budget $2,000. Quote?")
    assert lead["ai_status"] == "pending"
    event = db.scalar(
        select(OutboxEvent).where(OutboxEvent.payload["data"]["lead_id"].astext == lead["id"])
    )
    assert event is not None and event.event_type == "lead.created"


def test_same_email_or_phone_merges_instead_of_duplicating(client, db, owner):
    first = new_lead(client, phone="(415) 555-0132")
    by_email = new_lead(client, email="AMIRA@example.com", full_name="A. Hassan")
    by_phone = new_lead(client, email=None, phone="+1 415 555 0132", full_name="Someone")
    assert by_email["merged"] and by_email["id"] == first["id"]
    assert by_phone["merged"] and by_phone["id"] == first["id"]
    org_id = uuid.UUID(owner["organization_id"])
    assert (
        db.scalar(select(func.count()).select_from(Lead).where(Lead.organization_id == org_id)) == 1
    )


def test_editing_email_to_one_already_used_conflicts(client, owner):
    new_lead(client)
    other = new_lead(client, email="tomas@example.com", full_name="Tomas Rivera")
    resp = client.patch(f"/api/v1/leads/{other['id']}", json={"email": "amira@example.com"})
    assert resp.status_code == 409


def test_search_finds_by_name_company_email_and_typo(client, owner):
    new_lead(client)
    new_lead(client, email="tomas@example.com", full_name="Tomas Rivera", company="Rivera Auto")

    def names(q):
        return {
            i["full_name"] for i in client.get("/api/v1/leads", params={"q": q}).json()["items"]
        }

    assert names("cedar") == {"Amira Hassan"}
    assert names("tomas@") == {"Tomas Rivera"}
    assert "Amira Hassan" in names("Amira Hasan")  # one letter off still matches (trigram)


def test_filters_sort_and_pagination(client, db, owner):
    org_id = uuid.UUID(owner["organization_id"])
    for i, (prio, score) in enumerate([("high", 91), ("medium", 64), ("low", 20)]):
        lead = new_lead(client, email=f"l{i}@example.com", full_name=f"Lead {i}")
        row = db.get(Lead, uuid.UUID(lead["id"]))
        row.priority, row.score = prio, score
    db.flush()
    high = client.get("/api/v1/leads", params={"priority": "high"}).json()
    assert [i["score"] for i in high["items"]] == [91]
    by_score = client.get("/api/v1/leads", params={"sort": "score"}).json()["items"]
    assert [i["score"] for i in by_score] == [91, 64, 20]
    page2 = client.get("/api/v1/leads", params={"sort": "score", "page_size": 2, "page": 2}).json()
    assert page2["total"] == 3 and [i["score"] for i in page2["items"]] == [20]
    assert (
        db.scalar(select(func.count()).select_from(Lead).where(Lead.organization_id == org_id)) == 3
    )


def test_stage_change_and_assignment_write_the_timeline(client, owner):
    lead = new_lead(client)
    moved = client.post(
        f"/api/v1/leads/{lead['id']}/stage", json={"stage_id": stages(client)["qualified"]}
    ).json()
    assert moved["stage"]["key"] == "qualified"
    assigned = client.post(
        f"/api/v1/leads/{lead['id']}/assign", json={"user_id": owner["user_id"]}
    ).json()
    assert assigned["assigned_to"]["name"] == "Jordan Lee"
    mine = client.get("/api/v1/leads", params={"assigned": "me"}).json()["items"]
    assert [i["id"] for i in mine] == [lead["id"]]
    types = [a["type"] for a in client.get(f"/api/v1/leads/{lead['id']}/activities").json()]
    assert {"lead_created", "stage_changed", "assigned"} <= set(types)


def test_cannot_assign_to_someone_outside_the_organization(client, db, owner):
    lead = new_lead(client)
    outsider = User(email="out@example.com", full_name="Out")
    db.add(outsider)
    db.flush()
    resp = client.post(f"/api/v1/leads/{lead['id']}/assign", json={"user_id": str(outsider.id)})
    assert resp.status_code == 422


def test_notes_are_plain_text_and_listed_newest_first(client, owner):
    lead = new_lead(client)
    client.post(f"/api/v1/leads/{lead['id']}/notes", json={"body": "First call went well."})
    client.post(f"/api/v1/leads/{lead['id']}/notes", json={"body": "<b>Send quote</b>"})
    notes = client.get(f"/api/v1/leads/{lead['id']}/notes").json()
    assert [n["body"] for n in notes] == ["<b>Send quote</b>", "First call went well."]
    assert notes[0]["author"] == "Jordan Lee"


def test_archive_hides_restore_returns_and_frees_email(client, owner):
    lead = new_lead(client)
    client.post(f"/api/v1/leads/{lead['id']}/archive")
    assert client.get("/api/v1/leads").json()["total"] == 0
    assert client.get("/api/v1/leads", params={"archived": True}).json()["total"] == 1
    fresh = new_lead(client)  # same email allowed while the old one is archived
    assert fresh["id"] != lead["id"]
    assert client.post(f"/api/v1/leads/{lead['id']}/restore").status_code == 409


def test_erasure_is_admin_only_removes_data_and_keeps_anonymous_audit(client, db, owner):
    lead = new_lead(client, message="Private details here.")
    member = User(email="m@example.com", full_name="Member", password_hash=hash_password(PW))
    db.add(member)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=uuid.UUID(owner["organization_id"]), user_id=member.id, role="member"
        )
    )
    db.flush()
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "m@example.com", "password": PW})
    assert client.delete(f"/api/v1/leads/{lead['id']}").status_code == 403
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "jordan@example.com", "password": PW})
    assert client.delete(f"/api/v1/leads/{lead['id']}").status_code == 204
    lead_id = uuid.UUID(lead["id"])
    assert db.get(Lead, lead_id) is None
    assert (
        db.scalar(
            select(func.count()).select_from(LeadInquiry).where(LeadInquiry.lead_id == lead_id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count()).select_from(LeadActivity).where(LeadActivity.lead_id == lead_id)
        )
        == 0
    )
    row = db.scalar(select(AuditLog).where(AuditLog.entity_id == lead_id))
    assert row.action == "lead.erased"
    assert "amira" not in str(row.summary).lower()


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("get", "", None),
        ("patch", "", {"full_name": "x"}),
        ("post", "/archive", None),
        ("post", "/notes", {"body": "x"}),
        ("get", "/notes", None),
        ("get", "/activities", None),
        ("get", "/inquiries", None),
        ("delete", "", None),
    ],
)
def test_other_organization_gets_404_on_every_lead_route(client, owner, method, suffix, body):
    lead = new_lead(client)
    client.cookies.clear()
    client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Co",
            "full_name": "Eve",
            "email": "eve@example.com",
            "password": PW,
        },
    )
    resp = getattr(client, method)(
        f"/api/v1/leads/{lead['id']}{suffix}", **({"json": body} if body else {})
    )
    assert resp.status_code == 404


def test_stage_from_another_organization_is_rejected(client, owner):
    lead = new_lead(client)
    client.cookies.clear()
    client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Co",
            "full_name": "Eve",
            "email": "eve@example.com",
            "password": PW,
        },
    )
    foreign_stage = stages(client)["won"]
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "jordan@example.com", "password": PW})
    resp = client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage_id": foreign_stage})
    assert resp.status_code == 404
