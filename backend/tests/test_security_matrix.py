"""P10 gate: authorization matrix (endpoint × role) and isolation matrix (org B never reaches org
A's records, on every resource endpoint), plus security headers."""

import uuid

import pytest

from app.models import (
    CommunicationDraft,
    DuplicateCandidate,
    FollowUp,
    Invitation,
    Lead,
    ReportSnapshot,
)
from tests.test_org import PW, add_member, login_as, signup

# (method, path, body, minimum role). "member" means any logged-in member.
MATRIX = [
    ("get", "/api/v1/leads", None, "member"),
    ("post", "/api/v1/leads", {"full_name": "Matrix Lead"}, "member"),
    ("get", "/api/v1/drafts", None, "member"),
    ("get", "/api/v1/follow-ups", None, "member"),
    ("get", "/api/v1/analytics/overview", None, "member"),
    ("get", "/api/v1/analytics/sources", None, "member"),
    ("get", "/api/v1/analytics/funnel", None, "member"),
    ("get", "/api/v1/analytics/team", None, "member"),
    ("get", "/api/v1/analytics/reports", None, "member"),
    ("get", "/api/v1/settings/scoring", None, "member"),
    ("get", "/api/v1/settings/ai", None, "member"),
    ("get", "/api/v1/settings/notifications", None, "member"),
    ("get", "/api/v1/automation/overview", None, "member"),
    ("get", "/api/v1/integrations", None, "member"),
    ("post", "/api/v1/ai/analyze-text", {"message": "Need a website"}, "member"),
    ("get", "/api/v1/org/members", None, "member"),
    ("patch", "/api/v1/org", {"name": "Renamed"}, "admin"),
    ("post", "/api/v1/settings/services", {"name": "Matrix Service"}, "admin"),
    ("post", "/api/v1/settings/pipeline", {"label": "Matrix Stage"}, "admin"),
    ("put", "/api/v1/settings/ai", {"default_style": "concise", "daily_cap": 5}, "admin"),
    ("put", "/api/v1/settings/follow-ups", {"max_attempts": 3, "cooldown_days": 3}, "admin"),
    ("put", "/api/v1/settings/notifications", {"alert_on_high": True}, "admin"),
    ("put", "/api/v1/settings/retention", {"erase_archived_after_days": 365}, "admin"),
    ("post", "/api/v1/settings/retention/purge", None, "admin"),
    ("post", "/api/v1/settings/scoring/rescore", None, "admin"),
    ("get", "/api/v1/org/invitations", None, "admin"),
    ("post", "/api/v1/org/invitations", {"email": "matrix@example.com"}, "admin"),
    ("get", "/api/v1/leads/export", None, "admin"),
    ("post", "/api/v1/duplicates/scan", None, "admin"),
    ("post", "/api/v1/automation/outbox/redispatch", None, "admin"),
    ("post", "/api/v1/integrations/telegram/test", None, "admin"),
    ("post", "/api/v1/analytics/reports/daily", None, "admin"),
]
RANK = {"member": 1, "admin": 2, "owner": 3}


@pytest.fixture
def team(client, db, monkeypatch):
    from app.services import outbox

    monkeypatch.setattr(outbox, "dispatch_once", lambda *a, **k: 0)  # never reach real n8n
    owner = signup(client, "owner@example.com", "Matrix Org")
    add_member(db, owner["organization_id"], "admin@example.com", "admin")
    add_member(db, owner["organization_id"], "member@example.com", "member")
    return owner


@pytest.mark.parametrize(
    ("method", "path", "body", "minimum"), MATRIX, ids=[f"{m.upper()} {p}" for m, p, _, _ in MATRIX]
)
def test_authorization_matrix(client, team, method, path, body, minimum):
    kwargs = {"json": body} if body is not None else {}
    client.cookies.clear()
    anon = getattr(client, method)(path, **kwargs)
    assert anon.status_code == 401, f"anonymous {method.upper()} {path} -> {anon.status_code}"
    for role in ("member", "admin", "owner"):
        login_as(client, f"{role}@example.com")
        r = getattr(client, method)(path, **kwargs)
        if RANK[role] >= RANK[minimum]:
            assert r.status_code not in (401, 403), (
                f"{role} {method.upper()} {path} -> {r.status_code}"
            )
        else:
            assert r.status_code == 403, f"{role} {method.upper()} {path} -> {r.status_code}"


def test_csrf_header_required_for_writes(client, team):
    login_as(client, "owner@example.com")
    r = client.post("/api/v1/leads", json={"full_name": "X"}, headers={"X-Requested-With": ""})
    assert r.status_code == 403


# ---------------------------------------------------------------- isolation


@pytest.fixture
def foreign(client, db):
    """Records in org A; the test then logs in as the owner of org B."""
    a = signup(client, "a-owner@example.com", "Org A")
    org_a = uuid.UUID(a["organization_id"])
    lead = Lead(organization_id=org_a, full_name="A lead", email="alead@example.com")
    other = Lead(organization_id=org_a, full_name="A lead two", email="alead2@example.com")
    db.add_all([lead, other])
    db.flush()
    draft = CommunicationDraft(
        organization_id=org_a,
        lead_id=lead.id,
        subject="s",
        body="b",
        style="professional",
        source="template",
    )
    fu = FollowUp(
        organization_id=org_a,
        lead_id=lead.id,
        status="scheduled",
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    inv = Invitation(
        organization_id=org_a,
        email="x@example.com",
        role="member",
        token_hash=uuid.uuid4().hex,
        expires_at=fu.due_at,
    )
    pair = DuplicateCandidate(
        organization_id=org_a,
        lead_a_id=min(lead.id, other.id),
        lead_b_id=max(lead.id, other.id),
        confidence=0.9,
        reasons=[],
    )
    snap = ReportSnapshot(
        organization_id=org_a,
        kind="daily",
        period_start=fu.due_at,
        period_end=fu.due_at,
        metrics={},
        narrative="x",
        narrative_source="template",
    )
    db.add_all([draft, fu, inv, pair, snap])
    db.flush()
    client.cookies.clear()
    signup(client, "b-owner@example.com", "Org B")
    return {
        "lead": lead.id,
        "other": other.id,
        "draft": draft.id,
        "fu": fu.id,
        "inv": inv.id,
        "pair": pair.id,
    }


ISOLATION = [
    ("get", "/api/v1/leads/{lead}", None),
    ("patch", "/api/v1/leads/{lead}", {"company": "stolen"}),
    ("get", "/api/v1/leads/{lead}/analysis", None),
    ("post", "/api/v1/leads/{lead}/reanalyze", None),
    ("post", "/api/v1/leads/{lead}/ask", {"question": "budget?"}),
    ("post", "/api/v1/leads/{lead}/drafts", {}),
    ("get", "/api/v1/leads/{lead}/contact-rules", None),
    ("post", "/api/v1/leads/{lead}/replied", {}),
    ("post", "/api/v1/leads/{lead}/opt-out", None),
    ("post", "/api/v1/leads/{lead}/follow-ups", {"due_at": "2030-01-01T10:00:00Z"}),
    ("get", "/api/v1/leads/{lead}/activities", None),
    ("delete", "/api/v1/leads/{lead}", None),
    ("get", "/api/v1/drafts/{draft}", None),
    ("patch", "/api/v1/drafts/{draft}", {"subject": "x", "body": "y"}),
    ("post", "/api/v1/drafts/{draft}/approve", None),
    ("post", "/api/v1/drafts/{draft}/reject", {"reason": "nope"}),
    ("post", "/api/v1/follow-ups/{fu}/skip", {"reason": "nope"}),
    ("post", "/api/v1/follow-ups/{fu}/prepare", None),
    ("delete", "/api/v1/org/invitations/{inv}", None),
    ("get", "/api/v1/duplicates/{pair}/preview?keep={lead}", None),
    ("post", "/api/v1/duplicates/{pair}/merge", {"keep_lead_id": "{lead}"}),
]


@pytest.mark.parametrize(
    ("method", "path", "body"), ISOLATION, ids=[f"{m.upper()} {p}" for m, p, _ in ISOLATION]
)
def test_isolation_matrix(client, db, foreign, method, path, body):
    url = path.format(**foreign)
    if isinstance(body, dict):
        body = {k: (v.format(**foreign) if isinstance(v, str) else v) for k, v in body.items()}
    r = getattr(client, method)(url, **({"json": body} if body is not None else {}))
    assert r.status_code == 404, f"{method.upper()} {url} -> {r.status_code}"
    # Nothing in org A changed.
    assert db.get(Lead, foreign["lead"]) is not None
    assert db.get(CommunicationDraft, foreign["draft"]).status == "pending_approval"


def test_org_b_lists_never_show_org_a(client, foreign):
    for path in (
        "/api/v1/leads",
        "/api/v1/drafts?status=all",
        "/api/v1/follow-ups?status=all",
        "/api/v1/analytics/reports",
        "/api/v1/duplicates",
    ):
        body = client.get(path).json()
        items = body["items"] if isinstance(body, dict) else body
        assert items == [], path


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Referrer-Policy"] == "no-referrer"


__all__ = ["PW"]
