"""Sample data: loads into the caller's org only, is scored offline, and can be removed."""

from sqlalchemy import func, select

from app.models import DuplicateCandidate, Lead, LeadAnalysis
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse


def test_load_scores_spreads_and_clears(client, db, owner):  # noqa: F811
    real = new_lead(client, full_name="Real Customer")
    resp = client.post("/api/v1/org/sample-data", json={"count": 12})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["leads"] == 14 and body["sample_leads"] == 14  # 12 + 2 near-duplicates
    rows = client.get("/api/v1/leads", params={"page_size": 100}).json()["items"]
    sample = [r for r in rows if r["id"] != real["id"]]
    assert all(r["score"] is not None for r in sample)
    assert len({r["stage"]["key"] for r in sample}) >= 3
    providers = set(db.scalars(select(LeadAnalysis.provider)))
    assert providers <= {"fake"}  # never spends the Gemini quota
    assert db.scalar(select(func.count()).select_from(DuplicateCandidate)) >= 1

    assert client.delete("/api/v1/org/sample-data").json()["removed"] == 14
    left = db.scalars(select(Lead.id)).all()
    assert left == [__import__("uuid").UUID(real["id"])]  # real lead untouched


def test_sample_data_is_refused_outside_development(client, owner, monkeypatch):  # noqa: F811
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "app_env", "production")
    assert client.post("/api/v1/org/sample-data", json={}).status_code == 403
    assert client.get("/api/v1/org/sample-data").json()["available"] is False
