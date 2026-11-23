"""P5 slice 3: analysis read API, re-analyze, and versioned scoring settings."""

import uuid

from app.models import Lead, Organization
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse

MSG = (
    "We need a new website with online ordering for our bakery. Budget around $2,000, "
    "live within a month. Can you send a quote?"
)


def test_reanalyze_then_read_facts_and_factors(client, owner):  # noqa: F811
    lead = new_lead(client, message=MSG)
    out = client.post(f"/api/v1/leads/{lead['id']}/reanalyze").json()
    assert out["ai_status"] == "done" and out["score"] is not None
    body = client.get(f"/api/v1/leads/{lead['id']}/analysis").json()
    a, s = body["analysis"], body["score"]
    assert a["provider"] == "fake" and a["status"] == "done"
    assert all(svc["evidence"] is None or svc["evidence"] in MSG for svc in a["facts"]["services"])
    assert len(s["factors"]) == 7
    assert {"key", "label", "points", "max", "reason"} <= set(s["factors"][0])
    assert sum(f["points"] for f in s["factors"]) >= s["total"]  # caps only ever lower it
    row = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert row["score"] == s["total"] and "needs_review" in row


def test_analysis_is_empty_before_any_run(client, owner):  # noqa: F811
    lead = new_lead(client)
    assert client.get(f"/api/v1/leads/{lead['id']}/analysis").json() == {
        "analysis": None,
        "score": None,
    }


def test_another_organizations_lead_is_404(client, db, owner):  # noqa: F811
    other = Organization(name="O", slug=f"o-{uuid.uuid4().hex[:6]}", public_form_key="pk_x1")
    db.add(other)
    db.flush()
    lead = Lead(organization_id=other.id, full_name="X")
    db.add(lead)
    db.flush()
    assert client.get(f"/api/v1/leads/{lead.id}/analysis").status_code == 404
    assert client.post(f"/api/v1/leads/{lead.id}/reanalyze").status_code == 404


def test_scoring_settings_are_versioned_and_validated(client, owner):  # noqa: F811
    cfg = client.get("/api/v1/settings/scoring").json()
    assert cfg["version"] == 1 and sum(cfg["weights"].values()) == 100
    bad = {**cfg["weights"], "budget_fit": 50}
    resp = client.put(
        "/api/v1/settings/scoring", json={"weights": bad, "thresholds": cfg["thresholds"]}
    )
    assert resp.status_code == 422 and "add up to 100" in resp.text
    weights = {**cfg["weights"], "budget_fit": 30, "engagement": 0}
    resp = client.put(
        "/api/v1/settings/scoring",
        json={
            "weights": weights,
            "thresholds": {"high_min": 75, "medium_min": 45},
            "ideal_industries": ["Bakery", " "],
        },
    )
    assert resp.status_code == 200
    new = resp.json()
    assert new["version"] == 2 and new["ideal_industries"] == ["Bakery"]
    assert client.get("/api/v1/settings/scoring").json()["version"] == 2


def test_new_config_is_used_by_the_next_score(client, owner):  # noqa: F811
    cfg = client.get("/api/v1/settings/scoring").json()
    client.put(
        "/api/v1/settings/scoring",
        json={"weights": cfg["weights"], "thresholds": {"high_min": 99, "medium_min": 98}},
    )
    lead = new_lead(client, message=MSG)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    score = client.get(f"/api/v1/leads/{lead['id']}/analysis").json()["score"]
    assert score["config_version"] == 2 and score["band"] == "low"


def test_bad_thresholds_rejected(client, owner):  # noqa: F811
    cfg = client.get("/api/v1/settings/scoring").json()
    resp = client.put(
        "/api/v1/settings/scoring",
        json={"weights": cfg["weights"], "thresholds": {"high_min": 40, "medium_min": 60}},
    )
    assert resp.status_code == 422
