"""P9: scoring preview, notifications, retention."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import AuditLog, Lead
from tests.test_approvals import MSG
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse


def test_scoring_preview_changes_nothing(client, db, owner):  # noqa: F811
    lead = new_lead(client, message=MSG)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    before = client.get(f"/api/v1/leads/{lead['id']}").json()["score"]
    cfg = client.get("/api/v1/settings/scoring").json()
    r = client.post(
        "/api/v1/settings/scoring/preview",
        json={"weights": cfg["weights"], "thresholds": {"high_min": 99, "medium_min": 98}},
    )
    body = r.json()
    assert r.status_code == 200 and body["rows"][0]["new_band"] == "low"
    assert body["rows"][0]["new_score"] == before and body["band_changes"] >= 1
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["priority"] != "low" or before < 50
    bad = client.post(
        "/api/v1/settings/scoring/preview",
        json={"weights": {**cfg["weights"], "urgency": 50}, "thresholds": cfg["thresholds"]},
    )
    assert bad.status_code == 422


def test_notifications_roundtrip(client, owner):  # noqa: F811
    assert client.get("/api/v1/settings/notifications").json()["alert_on_high"] is True
    r = client.put(
        "/api/v1/settings/notifications",
        json={
            "alert_on_high": False,
            "daily_report": True,
            "weekly_report": False,
            "alert_email": "team@example.com",
        },
    )
    assert r.status_code == 200
    assert client.get("/api/v1/settings/notifications").json()["weekly_report"] is False


def test_retention_purges_only_old_archived_leads(client, db, owner):  # noqa: F811
    assert client.post("/api/v1/settings/retention/purge").status_code == 409
    old = new_lead(client, full_name="Old", email="old@example.com")
    recent = new_lead(client, full_name="Recent", email="recent@example.com")
    for x in (old, recent):
        client.post(f"/api/v1/leads/{x['id']}/archive")
    db.get(Lead, uuid.UUID(old["id"])).archived_at = datetime.now(UTC) - timedelta(days=100)
    db.flush()
    r = client.put("/api/v1/settings/retention", json={"erase_archived_after_days": 90}).json()
    assert r["due_for_erasure"] == 1
    assert client.post("/api/v1/settings/retention/purge").json() == {"erased": 1}
    assert db.get(Lead, uuid.UUID(old["id"])) is None
    assert db.get(Lead, uuid.UUID(recent["id"])) is not None
    assert (
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "lead.erased")
        )
        == 1
    )
