"""Reports (master prompt §8.5, W8 and W10). SQL produces every number; the AI only writes prose,
and a validator checks every number in that prose against the metrics. If any number is not in
the metrics, or the AI is unavailable, a template summary is used instead."""

import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.provider import AIInvalidOutput, AIUnavailable
from app.ai.schemas import Strict
from app.models import CommunicationDraft, Lead, Organization, ReportSnapshot

DAILY_WINDOW = (time(8, 30), time(9, 30))  # local time, W8 runs hourly
WEEKLY_DAY = 0  # Monday


class NarrativeOutput(Strict):
    text: str = Field(max_length=900)


NARRATIVE_SYSTEM = """You write a short, plain summary of a sales report for a small business
owner. Use ONLY the numbers in <metrics>. Do not compute new numbers (no sums, percentages or
differences that are not listed). Do not invent causes. At most 80 words, no greeting, no
markdown. Return JSON {"text": "..."}."""


def _local(org: Organization, now: datetime) -> datetime:
    try:
        return now.astimezone(ZoneInfo(org.timezone or "UTC"))
    except Exception:  # noqa: BLE001
        return now.astimezone(UTC)


# ---------------------------------------------------------------- metrics (SQL only)


def daily_metrics(db: Session, org: Organization, start: datetime, end: datetime) -> dict:
    from app.api.v1.analytics import median_first_reply_minutes, source_rows

    in_window = (Lead.organization_id == org.id, Lead.created_at >= start, Lead.created_at < end)
    new = db.scalar(select(func.count()).select_from(Lead).where(*in_window)) or 0
    high = (
        db.scalar(select(func.count()).select_from(Lead).where(*in_window, Lead.priority == "high"))
        or 0
    )
    sent = (
        db.scalar(
            select(func.count())
            .select_from(CommunicationDraft)
            .where(
                CommunicationDraft.organization_id == org.id,
                CommunicationDraft.status == "sent",
                CommunicationDraft.sent_at >= start,
                CommunicationDraft.sent_at < end,
            )
        )
        or 0
    )
    waiting = (
        db.scalar(
            select(func.count())
            .select_from(CommunicationDraft)
            .where(
                CommunicationDraft.organization_id == org.id,
                CommunicationDraft.status == "pending_approval",
            )
        )
        or 0
    )
    median, _ = median_first_reply_minutes(db, org.id, start)
    top = next((r for r in source_rows(db, org.id, start) if r["leads"]), None)
    return {
        "new_leads": new,
        "high_priority": high,
        "emails_sent": sent,
        "drafts_waiting": waiting,
        "median_first_reply_minutes": round(median) if median is not None else None,
        "top_source": top["source"] if top else None,
        "top_source_leads": top["leads"] if top else 0,
    }


def source_metrics(db: Session, org: Organization, start: datetime) -> dict:
    from app.api.v1.analytics import source_rows

    rows = [r for r in source_rows(db, org.id, start) if r["leads"]]
    return {
        "sources": [
            {
                "source": r["source"],
                "leads": r["leads"],
                "high": r["high"],
                "won": r["won"],
                "conversion_percent": round(r["conversion"] * 100),
            }
            for r in rows
        ],
        "total_leads": sum(r["leads"] for r in rows),
        "period_days": 7,
    }


# ---------------------------------------------------------------- narrative + validator

_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")


def _allowed_numbers(metrics) -> set[str]:
    out: set[str] = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            out.add(f"{v:g}")
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            out.update(n.replace(",", "") for n in _NUMBER.findall(v))

    walk(metrics)
    return out


def validate_narrative(text: str, metrics: dict) -> dict:
    """Every number in the prose must be one of the metric values (years and dates aside)."""
    allowed = _allowed_numbers(metrics)
    found = [n.replace(",", "") for n in _NUMBER.findall(text)]
    unknown = sorted({n for n in found if f"{float(n):g}" not in allowed})
    return {"ok": not unknown, "numbers": found, "unknown": unknown}


def template_daily(m: dict) -> str:
    parts = [
        f"Yesterday: {m['new_leads']} new lead{'s' if m['new_leads'] != 1 else ''}, "
        f"{m['high_priority']} high priority."
    ]
    parts.append(
        f"{m['emails_sent']} approved email{'s' if m['emails_sent'] != 1 else ''} "
        f"sent; {m['drafts_waiting']} draft{'s' if m['drafts_waiting'] != 1 else ''} "
        "waiting for approval."
    )
    if m.get("median_first_reply_minutes") is not None:
        parts.append(f"Median time to first reply: {m['median_first_reply_minutes']} minutes.")
    if m.get("top_source"):
        parts.append(f"Most leads came from {m['top_source']} ({m['top_source_leads']}).")
    return " ".join(parts)


def template_sources(m: dict) -> str:
    if not m["sources"]:
        return f"No new leads in the last {m.get('period_days', 7)} days."
    lines = [f"Last {m.get('period_days', 7)} days: {m['total_leads']} new leads."]
    for s in m["sources"][:4]:
        lines.append(
            f"{s['source']}: {s['leads']} leads, {s['high']} high priority, "
            f"{s['won']} won ({s['conversion_percent']}% converted)."
        )
    return " ".join(lines)


def narrate(metrics: dict, template: str, provider=None) -> tuple[str, str, dict]:
    """(text, source, validation). Falls back to the template whenever validation fails."""
    import json

    from app.services.analysis import _provider_or_error

    p = provider or _provider_or_error()
    if isinstance(p, str) or getattr(p, "name", "") == "fake":
        return template, "template", {"ok": True, "reason": "template used"}
    try:
        r = p.generate(
            NARRATIVE_SYSTEM,
            f"<metrics>{json.dumps(metrics)}</metrics>",
            NarrativeOutput,
            temperature=0.2,
        )
    except (AIUnavailable, AIInvalidOutput) as exc:
        return template, "template", {"ok": True, "reason": f"AI unavailable: {exc}"[:200]}
    check = validate_narrative(r.output.text, metrics)
    if not check["ok"]:
        return template, "template", {**check, "reason": "numbers not in the metrics"}
    return r.output.text, "ai", check


# ---------------------------------------------------------------- snapshots (W8, W10)


def _snapshot(
    db: Session,
    org: Organization,
    kind: str,
    start: datetime,
    end: datetime,
    metrics: dict,
    template: str,
    provider=None,
) -> ReportSnapshot:
    existing = db.scalar(
        select(ReportSnapshot).where(
            ReportSnapshot.organization_id == org.id,
            ReportSnapshot.kind == kind,
            ReportSnapshot.period_start == start,
        )
    )
    if existing:
        return existing
    text, source, check = narrate(metrics, template, provider)
    snap = ReportSnapshot(
        organization_id=org.id,
        kind=kind,
        period_start=start,
        period_end=end,
        metrics=metrics,
        narrative=text,
        narrative_source=source,
        validation=check,
    )
    db.add(snap)
    db.commit()
    return snap


def daily_due(org: Organization, now: datetime) -> bool:
    local = _local(org, now)
    return DAILY_WINDOW[0] <= local.time() < DAILY_WINDOW[1]


def make_daily(
    db: Session, org: Organization, now: datetime | None = None, provider=None
) -> ReportSnapshot:
    """Yesterday in the organization's own timezone."""
    now = now or datetime.now(UTC)
    local = _local(org, now)
    start_local = datetime.combine(local.date() - timedelta(days=1), time.min, local.tzinfo)
    start, end = start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)
    m = daily_metrics(db, org, start, end)
    return _snapshot(db, org, "daily", start, end, m, template_daily(m), provider)


def weekly_due(org: Organization, now: datetime) -> bool:
    local = _local(org, now)
    return local.weekday() == WEEKLY_DAY and DAILY_WINDOW[0] <= local.time() < DAILY_WINDOW[1]


def make_source_performance(
    db: Session, org: Organization, now: datetime | None = None, provider=None
) -> ReportSnapshot:
    now = now or datetime.now(UTC)
    local = _local(org, now)
    end_local = datetime.combine(local.date(), time.min, local.tzinfo)
    start, end = (end_local - timedelta(days=7)).astimezone(UTC), end_local.astimezone(UTC)
    m = source_metrics(db, org, start)
    return _snapshot(db, org, "source_performance", start, end, m, template_sources(m), provider)


def as_email(snap: ReportSnapshot, org: Organization, link: str) -> dict:
    title = "Daily summary" if snap.kind == "daily" else "Lead sources, last 7 days"
    return {
        "snapshot_id": str(snap.id),
        "subject": f"Replyline · {org.name} · {title}",
        "text": f"{snap.narrative}\n\nOpen the dashboard: {link}",
    }


def snapshot_out(s: ReportSnapshot) -> dict:
    return {
        "id": str(s.id),
        "kind": s.kind,
        "period_start": s.period_start.isoformat(),
        "period_end": s.period_end.isoformat(),
        "metrics": s.metrics,
        "narrative": s.narrative,
        "narrative_source": s.narrative_source,
        "validation": s.validation,
        "created_at": s.created_at.isoformat(),
    }
