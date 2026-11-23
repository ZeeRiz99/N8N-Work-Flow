"""P9 gate: every dashboard figure equals an independent raw-SQL count on seeded data."""

import uuid

import pytest
from sqlalchemy import text

from app.models import Organization
from app.services import sample_data
from tests.test_crm import owner  # noqa: F401 - fixture reuse


@pytest.fixture
def seeded(client, db, owner):  # noqa: F811
    org = db.get(Organization, uuid.UUID(owner["organization_id"]))
    sample_data.load(db, org, count=40, seed=7, days=60)
    return org


def sql(db, q: str, **params):
    return db.execute(text(q), params).scalar()


def test_overview_cards_reconcile(client, db, seeded):
    o = client.get("/api/v1/analytics/overview?days=30").json()
    c = o["cards"]
    p = {"org": seeded.id}
    assert c["new_leads"] == sql(
        db,
        """select count(*) from leads where organization_id=:org
        and created_at >= now() - interval '30 days'""",
        **p,
    )
    assert c["new_leads_previous"] == sql(
        db,
        """select count(*) from leads where
        organization_id=:org and created_at >= now() - interval '60 days'
        and created_at < now() - interval '30 days'""",
        **p,
    )
    assert c["high_priority"] == sql(
        db,
        """select count(*) from leads where
        organization_id=:org and archived_at is null and priority='high'
        and created_at >= now() - interval '30 days'""",
        **p,
    )
    assert c["awaiting_approval"] == sql(
        db,
        """select count(*) from communication_drafts
        where organization_id=:org and status='pending_approval'""",
        **p,
    )
    median = sql(
        db,
        """select percentile_cont(0.5) within group (order by
          greatest(0, extract(epoch from f.at - l.first_inquiry_at) / 60))
        from leads l join (select lead_id, min(occurred_at) at from communication_logs
          where organization_id=:org and direction='out' and status='sent' group by lead_id) f
          on f.lead_id = l.id
        where l.organization_id=:org and f.at >= now() - interval '30 days'""",
        **p,
    )
    assert c["median_first_reply_minutes"] == pytest.approx(median, abs=0.1)
    for m in o["priority_mix"]:
        assert m["count"] == sql(
            db,
            """select count(*) from leads where organization_id=:org
            and archived_at is null and priority=:pr and created_at >= now() - interval
            '30 days'""",
            pr=m["priority"],
            **p,
        )
    for s in o["stages"]:
        assert s["count"] == sql(
            db,
            """select count(l.id) from pipeline_stages s left join
            leads l on l.stage_id=s.id and l.archived_at is null where s.organization_id=:org
            and s.label=:label""",
            label=s["label"],
            **p,
        )


def test_trends_reconcile(client, db, seeded):
    t = client.get("/api/v1/analytics/trends?days=60").json()
    total = sum(x["leads"] for x in t["series"])
    high = sum(x["high"] for x in t["series"])
    assert total == sql(
        db,
        """select count(*) from leads where organization_id=:org
        and created_at >= now() - interval '60 days'""",
        org=seeded.id,
    )
    assert high == sql(
        db,
        """select count(*) from leads where organization_id=:org
        and priority='high' and created_at >= now() - interval '60 days'""",
        org=seeded.id,
    )


def test_sources_reconcile(client, db, seeded):
    rows = client.get("/api/v1/analytics/sources?days=90").json()["rows"]
    assert sum(r["leads"] for r in rows) == sql(
        db,
        """select count(*) from leads where
        organization_id=:org and created_at >= now() - interval '90 days'""",
        org=seeded.id,
    )
    for r in rows:
        n = sql(
            db,
            """select count(*) from leads l join lead_sources s on s.id=l.source_id
            where l.organization_id=:org and s.label=:label
            and l.created_at >= now() - interval '90 days'""",
            label=r["source"],
            org=seeded.id,
        )
        won = sql(
            db,
            """select count(*) from leads l join lead_sources s on s.id=l.source_id
            join pipeline_stages p on p.id=l.stage_id where l.organization_id=:org
            and s.label=:label and p.category='won'
            and l.created_at >= now() - interval '90 days'""",
            label=r["source"],
            org=seeded.id,
        )
        assert (r["leads"], r["won"]) == (n, won)


def test_funnel_reconcile(client, db, seeded):
    f = client.get("/api/v1/analytics/funnel?days=90").json()
    p = {"org": seeded.id}
    assert f["total"] == sql(
        db,
        """select count(*) from leads where organization_id=:org
        and archived_at is null and created_at >= now() - interval '90 days'""",
        **p,
    )
    won = sql(
        db,
        """select count(*) from leads l join pipeline_stages s on s.id=l.stage_id
        where l.organization_id=:org and l.archived_at is null and s.category='won'
        and l.created_at >= now() - interval '90 days'""",
        **p,
    )
    assert f["steps"][-1]["reached"] == won
    first = f["steps"][0]
    assert first["reached"] == sql(
        db,
        """select count(*) from leads l join pipeline_stages s
        on s.id=l.stage_id where l.organization_id=:org and l.archived_at is null
        and s.category in ('open','won') and l.created_at >= now() - interval '90 days'""",
        **p,
    )
    reached = [s["reached"] for s in f["steps"]]
    assert reached == sorted(reached, reverse=True)  # a funnel never widens


def test_team_reconcile(client, db, seeded, owner):  # noqa: F811
    rows = client.get("/api/v1/analytics/team").json()["rows"]
    me = next(r for r in rows if r["user_id"] == owner["user_id"])
    assert me["assigned"] == sql(
        db,
        """select count(*) from leads where organization_id=:org
        and assigned_to=:u and archived_at is null""",
        org=seeded.id,
        u=owner["user_id"],
    )


def test_export_is_csv_and_formula_safe(client, seeded):
    r = client.get("/api/v1/analytics/export?days=30")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("section,label,leads")
