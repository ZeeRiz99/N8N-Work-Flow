"""Outbox dispatcher: delivers pending events to n8n webhooks, with bounded, backed-off retries.

Rows are claimed with FOR UPDATE SKIP LOCKED, so two dispatchers never send the same event at
the same moment. Delivery is at-least-once; n8n and the internal API are idempotent on event_id.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import OutboxEvent

logger = logging.getLogger("replyline.outbox")

WEBHOOK_PATHS = {"lead.created": "lead-created", "draft.approved": "draft-approved"}
BACKOFF_BASE_SECONDS = 15
BACKOFF_CAP_SECONDS = 600


def backoff_seconds(attempts: int) -> int:
    """15 s, 30 s, 60 s, ... capped at 10 minutes."""
    return min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_CAP_SECONDS)


def dispatch_once(db: Session, settings: Settings, client: httpx.Client, limit: int = 20) -> int:
    """Deliver up to `limit` due events. Returns how many were delivered."""
    now = datetime.now(UTC)
    events = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending", OutboxEvent.next_attempt_at <= now)
        .order_by(OutboxEvent.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    delivered = 0
    for event in events:
        path = WEBHOOK_PATHS.get(event.event_type)
        if path is None:
            event.status, event.last_error = "failed", f"no webhook for {event.event_type}"
            continue
        envelope = event.payload
        headers = {
            "X-Webhook-Secret": settings.n8n_webhook_secret,
            "X-Request-ID": envelope.get("request_id") or "-",
            "Idempotency-Key": envelope["event_id"],
        }
        event.attempts += 1
        try:
            resp = client.post(
                f"{settings.n8n_webhook_base}/{path}", json=envelope, headers=headers
            )
            ok = 200 <= resp.status_code < 300
            error = None if ok else f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            ok, error = False, type(exc).__name__

        if ok:
            event.status, event.delivered_at, event.last_error = "delivered", now, None
            delivered += 1
        elif event.attempts >= settings.outbox_max_attempts:
            event.status, event.last_error = "failed", error
            logger.warning("outbox event failed permanently", extra={"status": event.attempts})
        else:
            event.last_error = error
            event.next_attempt_at = now + timedelta(seconds=backoff_seconds(event.attempts))
    db.commit()
    return delivered


def redispatch_failed(db: Session) -> int:
    """Put failed events back in the queue (the sweeper's job; also a manual tool)."""
    result = db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.status == "failed")
        .values(status="pending", attempts=0, next_attempt_at=datetime.now(UTC))
    )
    db.commit()
    return result.rowcount or 0


class OutboxWorker:
    """Background thread: dispatches every few seconds, or right away when nudged."""

    def __init__(self, session_factory: sessionmaker[Session], settings: Settings) -> None:
        self._factory = session_factory
        self._settings = settings
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="outbox", daemon=True)
        self._thread.start()

    def nudge(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        timeout = httpx.Timeout(self._settings.outbox_http_timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            while not self._stop.is_set():
                try:
                    with self._factory() as db:
                        dispatch_once(db, self._settings, client)
                except Exception:  # noqa: BLE001 - never let the worker die
                    logger.exception("outbox dispatch loop error")
                self._wake.wait(self._settings.outbox_poll_seconds)
                self._wake.clear()
