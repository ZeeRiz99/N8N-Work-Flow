"""Shared counters in PostgreSQL (backlog #42, #43): exact under concurrency, across workers."""

import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core import counters


@pytest.fixture
def factory(engine):
    # Real commits from several connections (like several workers); rows removed afterwards.
    f = sessionmaker(bind=engine, expire_on_commit=False)
    tag = f"test-{uuid.uuid4().hex[:8]}"
    yield f, tag
    with f() as s:
        s.execute(text("DELETE FROM usage_counters WHERE scope LIKE :t"), {"t": f"{tag}%"})
        s.execute(text("DELETE FROM rate_limit_hits WHERE key LIKE :t"), {"t": f"{tag}%"})
        s.commit()


def _parallel(fn, n):
    results = []
    lock = threading.Lock()

    def run():
        r = fn()
        with lock:
            results.append(r)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_budget_slots_are_exact_under_concurrency(factory):
    f, tag = factory
    results = _parallel(lambda: counters.take_slot(tag, "2026-11-26", "gemini", 18, f), 30)
    assert results.count(True) == 18
    assert counters.get_count(tag, "2026-11-26", "gemini", f) == 18
    assert counters.take_slot(tag, "2026-11-27", "gemini", 18, f) is True  # a new quota day


def test_exhausted_budget_refuses_until_the_period_changes(factory):
    f, tag = factory
    counters.set_count(tag, "d1", "gemini", 10**6, f)
    assert counters.take_slot(tag, "d1", "gemini", 18, f) is False
    assert counters.take_slot(tag, "d2", "gemini", 18, f) is True


def test_rate_limit_is_shared_and_exact_under_concurrency(factory):
    f, tag = factory
    results = _parallel(lambda: counters.hit(f"{tag}:1.2.3.4", 10, 60, f), 25)
    assert results.count(True) == 10
    assert counters.hit(f"{tag}:5.6.7.8", 10, 60, f) is True  # other keys are independent


def test_budget_module_uses_the_database_store(factory, monkeypatch):
    from app.ai import budget
    from app.core.config import get_settings

    f, tag = factory
    monkeypatch.setattr(budget, "_SCOPE", tag)
    monkeypatch.setattr(counters, "get_session_factory", lambda: f)
    monkeypatch.setattr(get_settings(), "ai_usage_store", "db")
    assert budget.take(2) and budget.take(2) and not budget.take(2)
    assert budget.used() == 2


def test_rate_limiter_falls_back_to_memory_when_the_database_is_down(monkeypatch):
    from app.api.deps import RateLimiter
    from app.core.config import get_settings

    def broken(*a, **k):
        raise RuntimeError("database down")

    monkeypatch.setattr(get_settings(), "rate_limit_store", "db")
    monkeypatch.setattr(counters, "hit", broken)
    lim = RateLimiter("t")
    assert [lim.check("k", 2) for _ in range(3)] == [True, True, False]
