"""The AIProvider interface (D11, ADR 004). The pipeline only talks to this, never to an SDK."""

from dataclasses import dataclass
from typing import Protocol

from app.ai.schemas import AnalysisOutput


class AIUnavailable(Exception):
    """The provider could not answer (timeout, rate limit, outage, circuit open). Retry later."""


class AIInvalidOutput(Exception):
    """The provider answered, but not with valid, schema-matching JSON."""


@dataclass(frozen=True)
class AIResult:
    output: AnalysisOutput
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(Protocol):
    name: str

    def analyze(self, system: str, user: str) -> AIResult: ...
