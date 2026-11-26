"""Daily Gemini call budget shared by every process on this machine (backend, evals, CLI).

The free tier has a small daily quota that resets at midnight Pacific time. Every HTTP request
counts (retries too), so the provider asks for a slot before each one. Past the budget it
raises AIUnavailable and the normal fallbacks apply; nothing is lost and nothing waits.
The counter lives in PostgreSQL (`usage_counters`), shared by every worker, container and CLI
process, and it survives restarts (backlog #43). If the database is unreachable, a small JSON
file guarded by a lock file takes over; tests use the file (AI_USAGE_STORE=file).
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import REPO_ROOT, get_settings

log = logging.getLogger(__name__)
_SCOPE = "ai_budget"

# AI_USAGE_FILE overrides the location (the production image is read-only for its user).
USAGE_FILE = Path(os.environ.get("AI_USAGE_FILE") or REPO_ROOT / ".ai-usage.json")
_LOCK = USAGE_FILE.with_suffix(".lock")
_PACIFIC = ZoneInfo("America/Los_Angeles")


def quota_day() -> str:
    return datetime.now(_PACIFIC).strftime("%Y-%m-%d")


class _FileLock:
    def __enter__(self):
        for _ in range(200):  # up to ~10 s
            try:
                self.fd = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except (FileExistsError, PermissionError):  # Windows: delete-pending file
                try:
                    if time.time() - _LOCK.stat().st_mtime > 30:  # stale lock from a crash
                        _LOCK.unlink(missing_ok=True)
                except FileNotFoundError:
                    pass  # released between our attempt and the check: just try again
                time.sleep(0.05)
        raise TimeoutError("AI usage lock busy")

    def __exit__(self, *exc):
        os.close(self.fd)
        _LOCK.unlink(missing_ok=True)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _file_used(provider: str) -> int:
    data = _read(USAGE_FILE)
    return int(data.get(quota_day(), {}).get(provider, 0))


def _file_take(budget: int, provider: str) -> bool:
    with _FileLock():
        data = _read(USAGE_FILE)
        day = quota_day()
        today = data.get(day, {})
        if int(today.get(provider, 0)) >= budget:
            return False
        today[provider] = int(today.get(provider, 0)) + 1
        USAGE_FILE.write_text(json.dumps({day: today}), encoding="utf-8")  # keep today only
        return True


def _file_exhaust(provider: str) -> None:
    with _FileLock():
        day = quota_day()
        data = _read(USAGE_FILE)
        today = data.get(day, {})
        today[provider] = 10**6
        USAGE_FILE.write_text(json.dumps({day: today}), encoding="utf-8")


def _use_db() -> bool:
    return get_settings().ai_usage_store == "db"


def used(provider: str = "gemini") -> int:
    if _use_db():
        try:
            from app.core import counters

            return counters.get_count(_SCOPE, quota_day(), provider)
        except Exception:  # noqa: BLE001
            log.warning("ai_budget_db_unavailable; reading the file counter")
    return _file_used(provider)


def take(budget: int, provider: str = "gemini") -> bool:
    """Reserve one call. False when today's budget is used up."""
    if budget <= 0:
        return False
    if _use_db():
        try:
            from app.core import counters

            return counters.take_slot(_SCOPE, quota_day(), provider, budget)
        except Exception:  # noqa: BLE001
            log.warning("ai_budget_db_unavailable; counting in the file")
    return _file_take(budget, provider)


def exhaust(provider: str = "gemini") -> None:
    """Google said the quota is gone: stop asking until the quota day changes."""
    if _use_db():
        try:
            from app.core import counters

            counters.set_count(_SCOPE, quota_day(), provider, 10**6)
            return
        except Exception:  # noqa: BLE001
            log.warning("ai_budget_db_unavailable; marking the file counter")
    _file_exhaust(provider)
