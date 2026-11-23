"""Automation Center and Integrations (master prompt §10 items 6 and 10; mockup 06)."""

import smtplib
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbSession, UserDep, csrf_protect
from app.core.config import get_settings
from app.models import (
    CommunicationDraft,
    Lead,
    LeadActivity,
    OutboxEvent,
    WorkflowExecution,
)
from app.services.outbox import redispatch_failed

router = APIRouter(tags=["automation"], dependencies=[Depends(csrf_protect)])

WORKFLOWS = [
    (
        "W1",
        "Lead Intake & Orchestration",
        "Every new inquiry: analyze, alert if High, draft a reply",
    ),
    ("W4b", "Send Approved Draft", "When someone approves a draft: send it once by email"),
    ("W9", "Error Monitor", "When any workflow fails: log it and alert the admin (throttled)"),
]


def _n8n_base() -> str:
    u = urlparse(get_settings().n8n_webhook_base)
    return f"{u.scheme}://{u.netloc}"


def _n8n_status() -> dict:
    try:
        r = httpx.get(f"{_n8n_base()}/healthz", timeout=3)
        return {"ok": r.status_code == 200, "detail": f"HTTP {r.status_code}"}
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": type(exc).__name__}


@router.get("/automation/overview")
def automation_overview(user: UserDep, db: DbSession) -> dict:
    org = user.organization_id
    since = datetime.now(UTC) - timedelta(days=7)
    runs = db.execute(
        select(WorkflowExecution.workflow_key, WorkflowExecution.status, func.count())
        .where(WorkflowExecution.organization_id == org, WorkflowExecution.created_at >= since)
        .group_by(WorkflowExecution.workflow_key, WorkflowExecution.status)
    ).all()
    stats: dict[str, dict[str, int]] = {}
    for key, status, n in runs:
        stats.setdefault(key, {})[status] = n
    last = {
        key: (status, at)
        for key, status, at in db.execute(
            select(
                WorkflowExecution.workflow_key,
                WorkflowExecution.status,
                func.max(WorkflowExecution.created_at),
            )
            .where(WorkflowExecution.organization_id == org)
            .group_by(WorkflowExecution.workflow_key, WorkflowExecution.status)
            .order_by(func.max(WorkflowExecution.created_at))
        ).all()
    }

    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    drafts = CommunicationDraft
    journey = [
        {
            "key": "W1",
            "label": "New inquiries",
            "count": count(Lead, Lead.organization_id == org, Lead.created_at >= since),
        },
        {
            "key": "W2",
            "label": "Leads analyzed",
            # Distinct leads: re-analyses and re-scores are not new work for the journey.
            "count": db.scalar(
                select(func.count(func.distinct(LeadActivity.lead_id))).where(
                    LeadActivity.organization_id == org,
                    LeadActivity.type == "scored",
                    LeadActivity.created_at >= since,
                )
            )
            or 0,
        },
        {
            "key": "W3",
            "label": "Alerts (High only)",
            "count": count(
                LeadActivity,
                LeadActivity.organization_id == org,
                LeadActivity.type == "alert_sent",
                LeadActivity.created_at >= since,
            ),
        },
        {
            "key": "W4",
            "label": "Drafts written",
            "count": count(drafts, drafts.organization_id == org, drafts.created_at >= since),
        },
        {
            "key": "you",
            "label": "You approved",
            "count": count(drafts, drafts.organization_id == org, drafts.approved_at >= since),
        },
        {
            "key": "W4b",
            "label": "Emails sent",
            "count": count(
                drafts,
                drafts.organization_id == org,
                drafts.status == "sent",
                drafts.sent_at >= since,
            ),
        },
    ]
    recent = db.scalars(
        select(WorkflowExecution)
        .where(WorkflowExecution.organization_id == org)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(25)
    ).all()
    return {
        "n8n": {**_n8n_status(), "editor_url": get_settings().n8n_editor_url},
        "workflows": [
            {
                "key": key,
                "name": name,
                "purpose": purpose,
                "runs_7d": sum(stats.get(key, {}).values()),
                "success_7d": stats.get(key, {}).get("success", 0),
                "skipped_7d": stats.get(key, {}).get("skipped", 0),
                "failed_7d": stats.get(key, {}).get("failed", 0),
                "last_status": last.get(key, (None, None))[0],
                "last_run_at": last[key][1].isoformat() if key in last else None,
            }
            for key, name, purpose in WORKFLOWS
        ],
        "journey": journey,
        "outbox": {
            "pending": count(
                OutboxEvent, OutboxEvent.organization_id == org, OutboxEvent.status == "pending"
            ),
            "failed": count(
                OutboxEvent, OutboxEvent.organization_id == org, OutboxEvent.status == "failed"
            ),
        },
        "recent": [
            {
                "workflow_key": r.workflow_key,
                "status": r.status,
                "n8n_execution_id": r.n8n_execution_id,
                "request_id": r.request_id,
                "lead_id": str(r.lead_id) if r.lead_id else None,
                "error": r.error_message,
                "meta": r.meta or {},
                "created_at": r.created_at.isoformat(),
            }
            for r in recent
        ],
    }


@router.post("/automation/outbox/redispatch")
def automation_redispatch(request: Request, user: AdminDep, db: DbSession) -> dict:
    """Retry deliveries to n8n that gave up (the outbox keeps every event)."""
    count = redispatch_failed(db)
    worker = getattr(request.app.state, "outbox", None)
    if worker is not None:
        worker.nudge()
    return {"requeued": count}


# ---------------------------------------------------------------- integrations


def _integrations() -> list[dict]:
    s = get_settings()
    from app.ai import budget

    gemini_on = s.ai_provider == "gemini" and bool(s.gemini_api_key)
    return [
        {
            "kind": "n8n",
            "name": "n8n automation",
            "configured": True,
            "detail": f"Webhooks at {_n8n_base()}",
        },
        {
            "kind": "email",
            "name": "Email (SMTP)",
            "configured": True,
            "detail": f"{s.smtp_test_host}:{s.smtp_test_port} (Mailpit in development)",
        },
        {
            "kind": "gemini",
            "name": "Google Gemini",
            "configured": gemini_on,
            "detail": (
                f"{s.gemini_models[0]} · {budget.used()} of {s.gemini_daily_budget} calls "
                "used today"
            )
            if gemini_on
            else "Offline AI in use (no key or AI_PROVIDER=fake)",
        },
        {
            "kind": "telegram",
            "name": "Telegram alerts",
            "configured": bool(s.telegram_bot_token),
            "detail": "Bot connected"
            if s.telegram_bot_token
            else "Not set up yet: create a bot with BotFather, then add it in n8n. Email alerts "
            "are used until then.",
        },
    ]


@router.get("/integrations")
def list_integrations(user: UserDep) -> list[dict]:
    return _integrations()


@router.post("/integrations/{kind}/test")
def test_integration(kind: Literal["n8n", "email", "gemini", "telegram"], user: AdminDep) -> dict:
    s = get_settings()
    if kind == "n8n":
        st = _n8n_status()
        return {"ok": st["ok"], "detail": f"n8n health check: {st['detail']}"}
    if kind == "email":
        try:
            with smtplib.SMTP(s.smtp_test_host, s.smtp_test_port, timeout=5) as smtp:
                code, _ = smtp.ehlo()
            return {"ok": 200 <= code < 300, "detail": f"SMTP server answered ({code})"}
        except (OSError, smtplib.SMTPException) as exc:
            return {"ok": False, "detail": f"SMTP not reachable ({type(exc).__name__})"}
    if kind == "gemini":
        if not (s.ai_provider == "gemini" and s.gemini_api_key):
            return {"ok": False, "detail": "No Gemini key configured; the offline AI is used."}
        try:
            from google import genai

            genai.Client(api_key=s.gemini_api_key).models.get(model=s.gemini_models[0])
            return {
                "ok": True,
                "detail": f"Key accepted; {s.gemini_models[0]} is available "
                "(no generation call, quota untouched)",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"Gemini refused: {type(exc).__name__}"}
    if not s.telegram_bot_token:
        raise HTTPException(409, "Telegram is not set up yet.")
    try:
        r = httpx.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe", timeout=5)
        return {"ok": r.status_code == 200, "detail": f"Telegram answered HTTP {r.status_code}"}
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "detail": f"Telegram not reachable ({type(exc).__name__}); on this "
            "network it needs a system-wide VPN",
        }
