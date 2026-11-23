"""The AIProvider interface (D11, ADR 004). The pipeline only talks to this, never to an SDK."""

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


class AIUnavailable(Exception):
    """The provider could not answer (timeout, rate limit, outage, circuit open). Retry later."""


class AIInvalidOutput(Exception):
    """The provider answered, but not with valid, schema-matching JSON."""


@dataclass(frozen=True)
class AIResult:
    output: Any  # the validated schema instance (AnalysisOutput, DraftOutput, ...)
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(Protocol):
    name: str

    def analyze(self, system: str, user: str) -> AIResult: ...

    def generate(
        self, system: str, user: str, schema: type[BaseModel], temperature: float = 0
    ) -> AIResult: ...
