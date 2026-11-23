"""P7: Overview analytics reconcile with raw SQL on the same data."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import CommunicationLog, Lead
from tests.test_approvals import MSG, _service_key_for, queued, svc
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse


def test_overview_cards_match_sql(client, db, owner):  # noqa: F811
    for i in range(3):
        new_lead(client, full_name=f"Lead {i}", email=f"l{i}@example.com")
    o = client.get("/api/v1/analytics/overview?days=7").json()
    raw = db.scalar(select(func.count()).select_from(Lead))
    assert o["cards"]["new_leads"] == raw == 3
    assert sum(m["count"] for m in o["priority_mix"]) == 3
    assert abs(sum(m["share"] for m in o["priority_mix"]) - 1) < 0.01
    assert sum(s["count"] for s in o["stages"]) == 3
    assert len(o["latest"]) == 3


def test_median_first_reply_and_next_step(client, db, owner):  # noqa: F811
    key = _service_key_for(db, owner)
    lead, d = queued(client)
    o = client.get("/api/v1/analytics/overview").json()
    assert o["cards"]["awaiting_approval"] == 1
    assert o["latest"][0]["next_step"] == "Approve the reply draft"
    row = db.get(Lead, __import__("uuid").UUID(lead["id"]))
    row.first_inquiry_at = datetime.now(UTC) - timedelta(minutes=90)
    db.flush()
    client.post(f"/api/v1/drafts/{d['id']}/approve")
    client.post(f"/api/v1/internal/drafts/{d['id']}/claim-send", headers=svc(key))
    client.post(f"/api/v1/internal/drafts/{d['id']}/mark-sent", json={}, headers=svc(key))
    o = client.get("/api/v1/analytics/overview").json()
    assert 89 <= o["cards"]["median_first_reply_minutes"] <= 91
    assert o["cards"]["answered_leads"] == 1 and o["automation_week"]["emails_sent"] == 1
    assert o["latest"][0]["next_step"].startswith("Follow up")
    assert db.scalar(select(func.count()).select_from(CommunicationLog)) == 1


def test_trends_has_every_day(client, owner):  # noqa: F811
    new_lead(client, message=MSG)
    t = client.get("/api/v1/analytics/trends?days=14").json()
    assert len(t["series"]) in (14, 15)
    assert sum(p["leads"] for p in t["series"]) == 1
