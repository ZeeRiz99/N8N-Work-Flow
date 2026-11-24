"""Daily Gemini call budget shared by every process on this machine (backend, evals, CLI).

The free tier has a small daily quota that resets at midnight Pacific time. Every HTTP request
counts (retries too), so the provider asks for a slot before each one. Past the budget it
raises AIUnavailable and the normal fallbacks apply; nothing is lost and nothing waits.
The counter lives in a small JSON file next to the repo (git-ignored), guarded by a lock file.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import REPO_ROOT

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


def used(provider: str = "gemini") -> int:
    data = _read(USAGE_FILE)
    return int(data.get(quota_day(), {}).get(provider, 0))


def take(budget: int, provider: str = "gemini") -> bool:
    """Reserve one call. False when today's budget is used up."""
    if budget <= 0:
        return False
    with _FileLock():
        data = _read(USAGE_FILE)
        day = quota_day()
        today = data.get(day, {})
        if int(today.get(provider, 0)) >= budget:
            return False
        today[provider] = int(today.get(provider, 0)) + 1
        USAGE_FILE.write_text(json.dumps({day: today}), encoding="utf-8")  # keep today only
        return True


def exhaust(provider: str = "gemini") -> None:
    """Google said the quota is gone: stop asking until the quota day changes."""
    with _FileLock():
        day = quota_day()
        data = _read(USAGE_FILE)
        today = data.get(day, {})
        today[provider] = 10**6
        USAGE_FILE.write_text(json.dumps({day: today}), encoding="utf-8")
