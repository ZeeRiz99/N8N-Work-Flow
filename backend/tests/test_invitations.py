"""P9 gate: invite and role flows."""

from sqlalchemy import select

from app.models import AuditLog, Invitation
from tests.test_crm import PW, owner  # noqa: F401 - fixture reuse


def _invite(client, email="new.member@example.com", role="member"):
    r = client.post("/api/v1/org/invitations", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


def test_invite_accept_creates_member_and_logs_in(client, db, owner):  # noqa: F811
    inv = _invite(client)
    token = inv["link"].rsplit("/", 1)[1]
    assert db.scalar(select(Invitation.token_hash)) != token  # only the hash is stored
    client.cookies.clear()
    info = client.get(f"/api/v1/auth/invitations/{token}").json()
    assert info["organization_name"] == "Harbor Test" and info["has_account"] is False
    me = client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "Nora Novak", "password": PW}
    )
    assert me.status_code == 200 and me.json()["role"] == "member"
    assert client.get("/api/v1/auth/me").json()["email"] == "new.member@example.com"
    # The link works once.
    assert client.get(f"/api/v1/auth/invitations/{token}").status_code == 410
    actions = set(db.scalars(select(AuditLog.action)))
    assert {"member.invited", "member.joined"} <= actions


def test_invite_rules(client, owner):  # noqa: F811
    assert (
        client.post(
            "/api/v1/org/invitations", json={"email": "x@example.com", "role": "owner"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/org/invitations", json={"email": "jordan@example.com", "role": "member"}
        ).status_code
        == 409
    )
    first = _invite(client, "twice@example.com")
    second = _invite(client, "twice@example.com", "admin")
    pending = client.get("/api/v1/org/invitations").json()
    assert [p["id"] for p in pending] == [second["id"]]  # re-inviting replaces the old link
    assert (
        client.get(f"/api/v1/auth/invitations/{first['link'].rsplit('/', 1)[1]}").status_code == 410
    )


def test_revoked_invite_cannot_be_used(client, owner):  # noqa: F811
    inv = _invite(client)
    assert client.delete(f"/api/v1/org/invitations/{inv['id']}").status_code == 204
    token = inv["link"].rsplit("/", 1)[1]
    client.cookies.clear()
    r = client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "X", "password": PW}
    )
    assert r.status_code == 409


def test_existing_account_must_prove_its_password(client, db, owner):  # noqa: F811
    from app.models import User
    from app.services.auth import hash_password

    db.add(User(email="existing@example.com", full_name="Ex", password_hash=hash_password(PW)))
    db.flush()
    inv = _invite(client, "existing@example.com")
    token = inv["link"].rsplit("/", 1)[1]
    client.cookies.clear()
    bad = client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"password": "Wrong-Password-123"}
    )
    assert bad.status_code == 409 and "password" in bad.text
    ok = client.post(f"/api/v1/auth/invitations/{token}/accept", json={"password": PW})
    assert ok.status_code == 200


def test_member_cannot_invite_and_role_change_applies(client, db, owner):  # noqa: F811
    inv = _invite(client)
    token = inv["link"].rsplit("/", 1)[1]
    client.cookies.clear()
    member = client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "Nora", "password": PW}
    ).json()
    assert (
        client.post("/api/v1/org/invitations", json={"email": "y@example.com"}).status_code == 403
    )
    # Owner promotes the member to admin; the new role applies on the next request.
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "jordan@example.com", "password": PW})
    members = client.get("/api/v1/org/members").json()
    target = next(m for m in members if m["user_id"] == member["user_id"])
    r = client.patch(f"/api/v1/org/members/{target['id']}", json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
