"""P5 gate: injected provider faults (timeout, 429, 5xx, malformed JSON) end in failed or
provisional states, never a crash or a lost lead. The SDK call is stubbed; no network."""

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors
from sqlalchemy import select

from app.ai import gemini_provider as gp
from app.ai.breaker import CircuitBreaker
from app.ai.provider import AIInvalidOutput, AIUnavailable
from app.models import Lead, LeadInquiry
from app.services import analysis

GOOD = json.dumps({"extraction": {}, "assessment": {"intent": "hiring", "summary": "ok"}})


class Script:
    """Plays a list of outcomes: an exception to raise, or a JSON string to return."""

    def __init__(self, *steps):
        self.steps, self.calls = list(steps), []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        step = self.steps.pop(0) if self.steps else self.steps_last
        self.steps_last = step
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(text=step, usage_metadata=None)


def make(script, breaker=None, attempts=3):
    p = gp.GeminiProvider(
        "test-key", "model-a", "model-b", 1, attempts, breaker or CircuitBreaker()
    )
    p._client = SimpleNamespace(models=script)
    return p


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gp.time, "sleep", lambda s: None)


def quota():
    return genai_errors.ClientError(429, {"error": {"code": 429, "message": "quota"}})


def server():
    return genai_errors.ServerError(503, {"error": {"code": 503, "message": "unavailable"}})


def test_429_is_retried_then_succeeds():
    s = Script(quota(), GOOD)
    out = make(s).analyze("sys", "user")
    assert out.output.assessment.intent == "hiring" and s.calls == ["model-a", "model-a"]


def test_persistent_5xx_falls_back_to_the_second_model():
    s = Script(server(), server(), server(), GOOD)
    out = make(s).analyze("sys", "user")
    assert out.model == "model-b"


def test_timeout_everywhere_raises_unavailable_not_a_crash():
    s = Script(*[httpx.ReadTimeout("slow")] * 6)
    with pytest.raises(AIUnavailable):
        make(s).analyze("sys", "user")
    assert len(s.calls) == 6  # 3 attempts on each model


def test_malformed_json_raises_invalid_output():
    with pytest.raises(AIInvalidOutput):
        make(Script("{not json")).analyze("sys", "user")


def test_unknown_fields_are_rejected():
    bad = json.dumps({"extraction": {}, "assessment": {}, "score": 100})
    with pytest.raises(AIInvalidOutput):
        make(Script(bad)).analyze("sys", "user")


def test_400_is_not_retried():
    bad_request = genai_errors.ClientError(400, {"error": {"code": 400, "message": "bad"}})
    s = Script(bad_request, bad_request)
    with pytest.raises(AIUnavailable):
        make(s).analyze("sys", "user")
    assert s.calls == ["model-a", "model-b"]


def test_circuit_opens_after_five_failures_and_skips_calls():
    breaker = CircuitBreaker(threshold=5, cooldown_seconds=60)
    s = Script(*[server()] * 100)
    p = make(s, breaker, attempts=1)
    for _ in range(5):
        with pytest.raises(AIUnavailable):
            p.analyze("sys", "user")
    before = len(s.calls)
    with pytest.raises(AIUnavailable, match="circuit open"):
        p.analyze("sys", "user")
    assert len(s.calls) == before


@pytest.mark.parametrize(
    "fault",
    [quota, server, lambda: httpx.ReadTimeout("slow"), lambda: "{broken"],
    ids=["429", "503", "timeout", "malformed"],
)
def test_pipeline_keeps_the_lead_with_a_provisional_score(db, org, monkeypatch, fault):
    script = Script(*[fault()] * 10)
    monkeypatch.setattr(analysis, "get_provider", lambda: make(script, attempts=1))
    lead = Lead(organization_id=org.id, full_name="Fault Test", email="f@example.com")
    db.add(lead)
    db.flush()
    db.add(LeadInquiry(organization_id=org.id, lead_id=lead.id, message="Need a website, $2,000"))
    db.flush()
    out = analysis.analyze_lead(db, org.id, lead.id)
    assert out["ai_status"] == "failed" and out["provisional"] is True
    assert db.scalar(select(Lead).where(Lead.id == lead.id)) is not None


# ---------------------------------------------------------------- daily budget


@pytest.fixture
def usage_file(tmp_path, monkeypatch):
    from app.ai import budget

    monkeypatch.setattr(budget, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(budget, "_LOCK", tmp_path / "usage.lock")
    return budget


def test_budget_stops_calls_at_the_limit(usage_file):
    s = Script(*[GOOD] * 10)
    p = make(s)
    p.daily_budget = 2
    p.analyze("sys", "user")
    p.analyze("sys", "user")
    with pytest.raises(AIUnavailable, match="budget"):
        p.analyze("sys", "user")
    assert len(s.calls) == 2 and usage_file.used() == 2


def test_quota_429_is_not_retried_and_closes_the_day(usage_file):
    exhausted = genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "You exceeded your current quota",
                "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
            }
        },
    )
    s = Script(exhausted, GOOD, GOOD)
    p = make(s)
    p.daily_budget = 10
    with pytest.raises(AIUnavailable, match="quota"):
        p.analyze("sys", "user")
    assert s.calls == ["model-a"]  # no retry, no fallback model
    with pytest.raises(AIUnavailable, match="budget"):
        p.analyze("sys", "user")
    assert s.calls == ["model-a"]
