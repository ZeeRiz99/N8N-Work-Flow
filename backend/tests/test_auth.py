"""Phase 4 slice 1: registration, login, cookies, CSRF, refresh rotation, reuse detection,
logout, login-required dashboard reads and tenant isolation."""

import uuid

from sqlalchemy import select

from app.models import Lead, Organization, OrganizationMember, RefreshToken, User
from app.services.auth import hash_password

GOOD_PASSWORD = "Sunrise-Bakery-2026"  # fictional test-only password  # gitleaks:allow


def register(client, email="owner@example.com", org="Harbor Web Studio"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org,
            "full_name": "Jordan Lee",
            "email": email,
            "password": GOOD_PASSWORD,
        },
    )


def make_member(db, org, email, role="member", password=GOOD_PASSWORD):
    user = User(email=email, full_name="Sara Khan", password_hash=hash_password(password))
    db.add(user)
    db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=role))
    db.flush()
    return user


def test_register_sets_httponly_cookies_and_returns_no_tokens(client):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "owner"
    assert "token" not in resp.text.lower()
    cookies = resp.headers.get_list("set-cookie")
    assert any(
        c.startswith("rl_access=") and "HttpOnly" in c and "SameSite=lax" in c for c in cookies
    )
    assert any(c.startswith("rl_refresh=") and "Path=/api/v1/auth" in c for c in cookies)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


def test_csrf_header_is_required_for_state_changes(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "x"},
        headers={"X-Requested-With": ""},
    )
    assert resp.status_code == 403


def test_foreign_origin_is_rejected(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "x"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_weak_password_is_rejected_without_echo(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "X Co",
            "full_name": "X",
            "email": "x@example.com",
            "password": "password",
        },
    )
    assert resp.status_code == 422
    assert "password" not in [d["message"] for d in resp.json()["error"]["details"]]
    assert '"password"' not in resp.text.split('"details"')[0]


def test_duplicate_email_registration_conflicts(client):
    register(client)
    assert register(client, org="Another Co").status_code == 409


def test_login_failures_share_one_generic_message(client, db, org):
    make_member(db, org, "sara@example.com")
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "sara@example.com", "password": "nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_login_rate_limit(client, db, org):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "z@example.com", "password": "nope"})
    resp = client.post("/api/v1/auth/login", json={"email": "z@example.com", "password": "nope"})
    assert resp.status_code == 429


def test_login_then_me(client, db, org):
    make_member(db, org, "sara@example.com", role="admin")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "SARA@example.com", "password": GOOD_PASSWORD}
    )
    assert resp.status_code == 200  # email lookup is case-insensitive (citext)
    me = client.get("/api/v1/auth/me").json()
    assert me["role"] == "admin" and me["organization_id"] == str(org.id)


def test_refresh_rotates_and_reuse_revokes_the_whole_family(client, db):
    register(client)
    old_refresh = client.cookies.get("rl_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 204
    new_refresh = client.cookies.get("rl_refresh")
    assert new_refresh and new_refresh != old_refresh

    # Someone replays the old (already rotated) token. Clear the jar so exactly one cookie is sent.
    client.cookies.clear()
    replay = client.post("/api/v1/auth/refresh", headers={"Cookie": f"rl_refresh={old_refresh}"})
    assert replay.status_code == 401
    # ...so the legitimate new token is dead too.
    client.cookies.clear()
    after = client.post("/api/v1/auth/refresh", headers={"Cookie": f"rl_refresh={new_refresh}"})
    assert after.status_code == 401
    live = db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))).all()
    assert live == []


def test_logout_revokes_refresh_and_clears_cookies(client, db):
    register(client)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert any("rl_access=" in c and "Max-Age=0" in c for c in resp.headers.get_list("set-cookie"))
    assert db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))).all() == []


def test_dashboard_reads_require_login(client):
    assert client.get("/api/v1/leads").status_code == 401


def test_tampered_access_token_is_rejected(client):
    register(client)
    token = client.cookies.get("rl_access")
    header, payload, signature = token.split(".")
    forged_sig = ("A" if signature[0] != "A" else "B") + signature[1:]
    client.cookies.clear()
    good = client.get("/api/v1/auth/me", headers={"Cookie": f"rl_access={token}"})
    assert good.status_code == 200
    forged = client.get(
        "/api/v1/auth/me", headers={"Cookie": f"rl_access={header}.{payload}.{forged_sig}"}
    )
    assert forged.status_code == 401


def test_removed_member_loses_access_immediately(client, db):
    register(client)
    me = client.get("/api/v1/auth/me").json()
    db.query(OrganizationMember).filter(
        OrganizationMember.user_id == uuid.UUID(me["user_id"])
    ).delete()
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_leads_list_only_shows_own_organization(client, db):
    register(client, email="a@example.com", org="Org A")
    org_a = db.scalar(select(Organization).where(Organization.name == "Org A"))
    org_b = Organization(name="Org B", slug=f"b-{uuid.uuid4().hex[:6]}", public_form_key="pk_b1")
    db.add(org_b)
    db.flush()
    db.add_all(
        [
            Lead(organization_id=org_a.id, full_name="Mine", email="m@example.com"),
            Lead(organization_id=org_b.id, full_name="Theirs", email="t@example.com"),
        ]
    )
    db.flush()
    names = [item["full_name"] for item in client.get("/api/v1/leads").json()["items"]]
    assert names == ["Mine"]
