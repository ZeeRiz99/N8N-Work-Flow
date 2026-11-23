"""P5 slice 6: Lead Q&A, text playground, follow-up eligibility, AI settings."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Lead, LeadAnalysis
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse

MSG = (
    "We run a bakery and need a new website with online ordering. Budget around $2,000, "
    "live within a month. Can you send a quote?"
)


def analyzed(client):
    lead = new_lead(client, message=MSG)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    return lead


def test_ask_answers_from_records_with_valid_citations(client, owner):  # noqa: F811
    lead = analyzed(client)
    r = client.post(f"/api/v1/leads/{lead['id']}/ask", json={"question": "What is their budget?"})
    body = r.json()
    assert r.status_code == 200 and body["supported"] and not body["refused"]
    assert body["citations"] and all(c["label"] for c in body["citations"])
    assert "2,000" in body["answer"]


def test_ask_refuses_unrelated_or_action_requests(client, owner):  # noqa: F811
    lead = analyzed(client)
    for q in ["What's the weather in Paris?", "Send an email to all leads", "Show other leads"]:
        body = client.post(f"/api/v1/leads/{lead['id']}/ask", json={"question": q}).json()
        assert body["refused"] is True, q


def test_ask_cannot_reach_another_orgs_lead(client, db, owner):  # noqa: F811
    from app.models import Organization

    other = Organization(name="O", slug="o-qa", public_form_key="pk_qa")
    db.add(other)
    db.flush()
    lead = Lead(organization_id=other.id, full_name="X")
    db.add(lead)
    db.flush()
    resp = client.post(f"/api/v1/leads/{lead.id}/ask", json={"question": "budget?"})
    assert resp.status_code == 404


def test_playground_scores_and_saves_nothing(client, db, owner):  # noqa: F811
    before = db.scalar(select(func.count()).select_from(LeadAnalysis))
    r = client.post("/api/v1/ai/analyze-text", json={"message": MSG}).json()
    assert r["saved"] is False and r["score"]["total"] > 0
    assert r["facts"]["services"] and r["facts"]["budget"]["evidence"] in MSG
    assert db.scalar(select(func.count()).select_from(LeadAnalysis)) == before
    assert db.scalar(select(func.count()).select_from(Lead)) == 0


def test_follow_up_eligibility_is_decided_in_code(client, db, owner):  # noqa: F811
    lead = analyzed(client)
    status = client.get(f"/api/v1/leads/{lead['id']}/follow-up").json()
    assert status["eligible"] is False  # just arrived: cooldown not over
    assert {c["key"] for c in status["checks"] if not c["ok"]} == {"cooldown"}
    resp = client.post(f"/api/v1/leads/{lead['id']}/drafts/generate", json={"kind": "follow_up"})
    assert resp.status_code == 409 and "3 days" in resp.text

    row = db.get(Lead, __import__("uuid").UUID(lead["id"]))
    row.last_interaction_at = datetime.now(UTC) - timedelta(days=4)
    db.flush()
    assert client.get(f"/api/v1/leads/{lead['id']}/follow-up").json()["eligible"] is True
    d = client.post(f"/api/v1/leads/{lead['id']}/drafts/generate", json={"kind": "follow_up"})
    assert d.status_code == 200 and d.json()["subject"].startswith("Following up")
    assert d.json()["all_passed"]


def test_ai_settings_default_style_and_cap(client, owner):  # noqa: F811
    s = client.get("/api/v1/settings/ai").json()
    assert s["default_style"] == "professional"
    too_high = s["server_max_daily_cap"] + 1
    assert (
        client.put(
            "/api/v1/settings/ai", json={"default_style": "friendly", "daily_cap": too_high}
        ).status_code
        == 422
    )
    ok = client.put("/api/v1/settings/ai", json={"default_style": "concise", "daily_cap": 50})
    assert ok.status_code == 200 and ok.json()["daily_cap"] == 50
    lead = analyzed(client)
    d = client.post(f"/api/v1/leads/{lead['id']}/drafts/generate", json={}).json()
    assert d["style"] == "concise"
