"""Phase 4 slice 2: organization profile, team roles, pipeline, sources, services, and the
tenant-isolation matrix (org B can never read or change org A's records)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Lead, LeadSource, OrganizationMember, PipelineStage, Service, User
from app.services.auth import hash_password
from app.services.normalize import normalize_phone

PW = "Sunrise-Bakery-2026"  # fictional test-only password  # gitleaks:allow


def signup(client: TestClient, email: str, org: str) -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"organization_name": org, "full_name": "Owner", "email": email, "password": PW},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_member(db, org_id, email, role):
    user = User(email=email, full_name=email.split("@")[0], password_hash=hash_password(PW))
    db.add(user)
    db.flush()
    m = OrganizationMember(organization_id=uuid.UUID(org_id), user_id=user.id, role=role)
    db.add(m)
    db.flush()
    return m


def login_as(client, email):
    client.cookies.clear()
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": PW}).status_code == 200
    )


# ---------------------------------------------------------------- defaults and profile


def test_new_org_gets_default_stages_and_sources(client):
    signup(client, "o@example.com", "Org One")
    stages = client.get("/api/v1/settings/pipeline").json()
    assert [s["key"] for s in stages][:2] == ["new", "ai_processed"]
    assert {s["category"] for s in stages} == {"open", "won", "lost"}
    assert all(s["is_system"] for s in stages)
    assert {s["key"] for s in client.get("/api/v1/settings/sources").json()} >= {"form", "csv"}


def test_admin_updates_business_profile_and_bad_timezone_is_rejected(client):
    signup(client, "o@example.com", "Org One")
    ok = client.patch(
        "/api/v1/org",
        json={"timezone": "Asia/Karachi", "currency": "USD", "reply_target_minutes": 120},
    )
    assert ok.status_code == 200 and ok.json()["reply_target_minutes"] == 120
    bad = client.patch("/api/v1/org", json={"timezone": "Mars/Base"})
    assert bad.status_code == 422


def test_member_can_read_but_not_change_settings(client, db):
    me = signup(client, "o@example.com", "Org One")
    add_member(db, me["organization_id"], "m@example.com", "member")
    login_as(client, "m@example.com")
    assert client.get("/api/v1/settings/pipeline").status_code == 200
    assert client.patch("/api/v1/org", json={"name": "Hacked"}).status_code == 403
    assert client.post("/api/v1/settings/services", json={"name": "X"}).status_code == 403


# ---------------------------------------------------------------- roles


def test_last_owner_cannot_be_demoted_or_removed(client, db):
    me = signup(client, "o@example.com", "Org One")
    owner = db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == uuid.UUID(me["user_id"]))
    )
    assert (
        client.patch(f"/api/v1/org/members/{owner.id}", json={"role": "admin"}).status_code == 409
    )
    assert client.delete(f"/api/v1/org/members/{owner.id}").status_code == 409


def test_admin_cannot_grant_owner_but_owner_can(client, db):
    me = signup(client, "o@example.com", "Org One")
    admin = add_member(db, me["organization_id"], "a@example.com", "admin")
    member = add_member(db, me["organization_id"], "m@example.com", "member")
    login_as(client, "a@example.com")
    assert (
        client.patch(f"/api/v1/org/members/{member.id}", json={"role": "owner"}).status_code == 403
    )
    assert (
        client.patch(f"/api/v1/org/members/{member.id}", json={"role": "admin"}).status_code == 200
    )
    login_as(client, "o@example.com")
    assert (
        client.patch(f"/api/v1/org/members/{admin.id}", json={"role": "owner"}).status_code == 200
    )


def test_demoted_member_loses_admin_rights_on_next_request(client, db):
    me = signup(client, "o@example.com", "Org One")
    admin = add_member(db, me["organization_id"], "a@example.com", "admin")
    login_as(client, "a@example.com")
    assert client.patch("/api/v1/org", json={"name": "Renamed"}).status_code == 200
    admin.role = "member"
    db.flush()
    assert client.patch("/api/v1/org", json={"name": "Again"}).status_code == 403


# ---------------------------------------------------------------- pipeline and services


def test_custom_stage_lifecycle_and_system_stage_protection(client, db):
    signup(client, "o@example.com", "Org One")
    new = client.post("/api/v1/settings/pipeline", json={"label": "Negotiation"}).json()
    assert new["key"] == "negotiation" and not new["is_system"]
    renamed = client.patch(f"/api/v1/settings/pipeline/{new['id']}", json={"label": "Talks"}).json()
    assert renamed["key"] == "negotiation" and renamed["label"] == "Talks"  # key stays stable
    system = client.get("/api/v1/settings/pipeline").json()[0]
    assert client.delete(f"/api/v1/settings/pipeline/{system['id']}").status_code == 409
    assert client.delete(f"/api/v1/settings/pipeline/{new['id']}").status_code == 204


def test_stage_with_leads_cannot_be_deleted(client, db):
    me = signup(client, "o@example.com", "Org One")
    stage = client.post("/api/v1/settings/pipeline", json={"label": "Hold"}).json()
    db.add(
        Lead(
            organization_id=uuid.UUID(me["organization_id"]),
            full_name="L",
            stage_id=uuid.UUID(stage["id"]),
        )
    )
    db.flush()
    assert client.delete(f"/api/v1/settings/pipeline/{stage['id']}").status_code == 409


def test_service_price_range_is_validated_and_names_are_unique(client):
    signup(client, "o@example.com", "Org One")
    bad = client.post(
        "/api/v1/settings/services",
        json={"name": "Web", "price_min_minor": 500_000, "price_max_minor": 100_000},
    )
    assert bad.status_code == 422
    ok = client.post(
        "/api/v1/settings/services",
        json={
            "name": "Web",
            "keywords": [" Website ", ""],
            "price_min_minor": 150_000,
            "price_max_minor": 500_000,
        },
    )
    assert ok.status_code == 201 and ok.json()["keywords"] == ["website"]
    assert client.post("/api/v1/settings/services", json={"name": "web"}).status_code == 409


# ---------------------------------------------------------------- isolation matrix


@pytest.fixture
def two_orgs(client, db):
    """Org A's owner creates one of everything; then the client logs in as org B's owner."""
    a = signup(client, "a@example.com", "Org A")
    svc = client.post("/api/v1/settings/services", json={"name": "A service"}).json()
    stage = client.post("/api/v1/settings/pipeline", json={"label": "A stage"}).json()
    a_member = add_member(db, a["organization_id"], "a2@example.com", "member")
    lead = Lead(
        organization_id=uuid.UUID(a["organization_id"]),
        full_name="A lead",
        email="lead@example.com",
    )
    db.add(lead)
    db.flush()
    client.cookies.clear()
    signup(client, "b@example.com", "Org B")
    return {
        "service": svc["id"],
        "stage": stage["id"],
        "member": str(a_member.id),
        "lead": str(lead.id),
    }


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", "/api/v1/settings/services/{service}", {"name": "stolen"}),
        ("patch", "/api/v1/settings/pipeline/{stage}", {"label": "stolen"}),
        ("delete", "/api/v1/settings/pipeline/{stage}", None),
        ("patch", "/api/v1/org/members/{member}", {"role": "admin"}),
        ("delete", "/api/v1/org/members/{member}", None),
    ],
)
def test_org_b_cannot_touch_org_a_records(client, db, two_orgs, method, path, body):
    url = path.format(**two_orgs)
    resp = getattr(client, method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 404, f"{method.upper()} {url} -> {resp.status_code}"


def test_org_b_lists_never_include_org_a_rows(client, db, two_orgs):
    names = {s["name"] for s in client.get("/api/v1/settings/services").json()}
    labels = {s["label"] for s in client.get("/api/v1/settings/pipeline").json()}
    members = {m["email"] for m in client.get("/api/v1/org/members").json()}
    leads = {item["full_name"] for item in client.get("/api/v1/leads").json()["items"]}
    assert "A service" not in names and "A stage" not in labels
    assert members == {"b@example.com"} and "A lead" not in leads
    # And org A's rows are untouched by the attempts above.
    assert (
        db.scalar(select(Service.name).where(Service.id == uuid.UUID(two_orgs["service"])))
        == "A service"
    )
    assert (
        db.scalar(
            select(PipelineStage.label).where(PipelineStage.id == uuid.UUID(two_orgs["stage"]))
        )
        == "A stage"
    )
    assert db.scalar(select(LeadSource.id).limit(1)) is not None


# ---------------------------------------------------------------- normalization


@pytest.mark.parametrize(
    ("raw", "region", "expected"),
    [
        ("(415) 555-0132", "US", "+14155550132"),
        ("+44 20 7946 0958", "US", "+442079460958"),
        ("0300 1234567", "PK", "+923001234567"),
        ("not a phone", "US", None),
        ("", "US", None),
    ],
)
def test_phone_normalization(raw, region, expected):
    assert normalize_phone(raw, region) == expected
