"""P9 gate: narrative validator, report snapshots, W8/W10 local-time windows."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import func, select

from app.ai.provider import AIUnavailable
from app.models import Organization, ReportSnapshot
from app.services import reports
from tests.test_approvals import _service_key_for, svc
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse

METRICS = {
    "new_leads": 12,
    "high_priority": 3,
    "emails_sent": 5,
    "drafts_waiting": 2,
    "median_first_reply_minutes": 95,
    "top_source": "Web form",
    "top_source_leads": 7,
}


class Says:
    name = "gemini"

    def __init__(self, text):
        self.text = text

    def generate(self, system, user, schema, temperature=0):
        return SimpleNamespace(output=reports.NarrativeOutput(text=self.text))


class Down:
    name = "gemini"

    def generate(self, *a, **k):
        raise AIUnavailable("ClientError 429")


def test_validator_accepts_only_metric_numbers():
    ok = reports.validate_narrative("12 new leads, 3 high priority; 5 emails sent.", METRICS)
    assert ok["ok"] and ok["unknown"] == []
    bad = reports.validate_narrative("12 new leads, up 40% on last week.", METRICS)
    assert not bad["ok"] and bad["unknown"] == ["40"]
    derived = reports.validate_narrative("15 leads in total (12 + 3).", METRICS)
    assert derived["unknown"] == ["15"]


def test_narrate_falls_back_to_template_when_numbers_are_invented():
    template = reports.template_daily(METRICS)
    text, source, check = reports.narrate(METRICS, template, Says("You had 14 new leads."))
    assert source == "template" and text == template and check["unknown"] == ["14"]
    text, source, _ = reports.narrate(METRICS, template, Says("12 new leads; 5 emails went out."))
    assert source == "ai" and text.startswith("12 new leads")
    text, source, _ = reports.narrate(METRICS, template, Down())
    assert source == "template"


def test_template_numbers_always_validate():
    assert reports.validate_narrative(reports.template_daily(METRICS), METRICS)["ok"]
    sm = {
        "sources": [
            {"source": "Web form", "leads": 9, "high": 2, "won": 1, "conversion_percent": 11}
        ],
        "total_leads": 9,
        "period_days": 7,
    }
    assert reports.validate_narrative(reports.template_sources(sm), sm)["ok"]


def test_daily_snapshot_once_and_numbers_from_sql(client, db, owner):  # noqa: F811
    org = db.get(Organization, uuid.UUID(owner["organization_id"]))
    org.timezone = "Asia/Karachi"
    for i in range(3):
        new_lead(client, full_name=f"R {i}", email=f"r{i}@example.com")
    # Next day, 09:00 in Karachi = 04:00 UTC: "yesterday" holds the three leads.
    tomorrow_9am = datetime.now(UTC).replace(hour=4, minute=0) + __import__("datetime").timedelta(
        days=1
    )
    assert reports.daily_due(org, tomorrow_9am)
    snap = reports.make_daily(db, org, tomorrow_9am)
    again = reports.make_daily(db, org, tomorrow_9am)
    assert snap.id == again.id
    assert (
        snap.metrics["new_leads"]
        == db.execute(
            select(func.count())
            .select_from(__import__("app.models", fromlist=["Lead"]).Lead)
            .where(
                __import__("app.models", fromlist=["Lead"]).Lead.created_at >= snap.period_start,
                __import__("app.models", fromlist=["Lead"]).Lead.created_at < snap.period_end,
            )
        ).scalar()
    )
    assert reports.validate_narrative(snap.narrative, snap.metrics)["ok"]


def test_report_windows_follow_local_time():
    org = SimpleNamespace(timezone="America/Los_Angeles")
    # 2026-11-30 is a Monday. 09:00 in Los Angeles = 17:00 UTC.
    assert reports.daily_due(org, datetime(2026, 11, 30, 17, 0, tzinfo=UTC))
    assert not reports.daily_due(org, datetime(2026, 11, 30, 18, 30, tzinfo=UTC))
    assert reports.weekly_due(org, datetime(2026, 11, 30, 17, 0, tzinfo=UTC))
    assert not reports.weekly_due(org, datetime(2026, 12, 1, 17, 0, tzinfo=UTC))


def test_internal_daily_report_outside_window_is_empty(client, db, owner, monkeypatch):  # noqa: F811
    key = _service_key_for(db, owner)
    monkeypatch.setattr(reports, "daily_due", lambda org, now: False)
    assert client.get("/api/v1/internal/reports/daily", headers=svc(key)).json() == {"report": None}
    monkeypatch.setattr(reports, "daily_due", lambda org, now: True)
    first = client.get("/api/v1/internal/reports/daily", headers=svc(key)).json()
    second = client.get("/api/v1/internal/reports/daily", headers=svc(key)).json()
    assert first["report"]["subject"].startswith("Replyline") and second == {"report": None}
    assert db.scalar(select(func.count()).select_from(ReportSnapshot)) == 1
    listed = client.get("/api/v1/analytics/reports").json()
    assert len(listed) == 1 and listed[0]["narrative_source"] == "template"
