"""GeminiProvider: the ONLY module that imports Google's SDK (D11).

Structured output against the AnalysisOutput schema, temperature 0, a per-call timeout,
retries with backoff on 429/5xx (honouring Retry-After), a fallback model, and the circuit
breaker. The model receives no tools and no secrets.
"""

import time

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, ValidationError

from app.ai import budget
from app.ai.breaker import CircuitBreaker, gemini_breaker
from app.ai.provider import AIInvalidOutput, AIResult, AIUnavailable
from app.ai.schemas import AnalysisOutput

RETRYABLE = {429, 500, 502, 503, 504}
_SCHEMA = AnalysisOutput.model_json_schema()


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str | None = None,
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        breaker: CircuitBreaker = gemini_breaker,
        daily_budget: int | None = None,
    ) -> None:
        if not api_key:
            raise AIUnavailable("GEMINI_API_KEY is not set.")
        self._client = genai.Client(api_key=api_key)
        self.models = [m for m in (model, fallback_model) if m]
        self.timeout_ms = int(timeout_seconds * 1000)
        self.max_attempts = max_attempts
        self.breaker = breaker
        self.daily_budget = daily_budget  # None: no local budget (tests)

    def analyze(self, system: str, user: str) -> AIResult:
        return self.generate(system, user, AnalysisOutput)

    def generate(
        self, system: str, user: str, schema: type[BaseModel], temperature: float = 0
    ) -> AIResult:
        """One structured call: the reply must validate against `schema` (strict)."""
        json_schema = _SCHEMA if schema is AnalysisOutput else schema.model_json_schema()
        if not self.breaker.allow():
            raise AIUnavailable("circuit open after repeated provider failures")
        last: Exception | None = None
        for model in self.models:
            for attempt in range(1, self.max_attempts + 1):
                if self.daily_budget is not None and not budget.take(self.daily_budget):
                    raise AIUnavailable("daily Gemini budget reached; resets at midnight Pacific")
                start = time.perf_counter()
                try:
                    resp = self._client.models.generate_content(
                        model=model,
                        contents=user,
                        config={
                            "system_instruction": system,
                            "response_mime_type": "application/json",
                            # JSON Schema form: the SDK's typed form rejects the
                            # additionalProperties that our strict models emit.
                            "response_json_schema": json_schema,
                            "temperature": temperature,
                            "http_options": {"timeout": self.timeout_ms},
                        },
                    )
                except genai_errors.APIError as exc:
                    last = exc
                    code = getattr(exc, "code", None)
                    if code == 429 and "perday" in str(exc).lower():
                        # The DAILY quota is gone (per-minute limits are retried below).
                        if self.daily_budget is not None:
                            budget.exhaust()
                        self.breaker.failure()
                        raise AIUnavailable("Gemini daily quota exhausted") from exc
                    if code in RETRYABLE and attempt < self.max_attempts:
                        time.sleep(_retry_after(exc) or min(2**attempt, 8))
                        continue
                    break  # not retryable here: try the fallback model
                except Exception as exc:  # noqa: BLE001 - timeouts and network errors
                    last = exc
                    if attempt < self.max_attempts:
                        time.sleep(min(2**attempt, 8))
                        continue
                    break
                latency = round((time.perf_counter() - start) * 1000)
                try:
                    output = schema.model_validate_json(resp.text or "")
                except ValidationError as exc:
                    self.breaker.failure()
                    raise AIInvalidOutput(f"schema mismatch: {exc.error_count()} error(s)") from exc
                usage = getattr(resp, "usage_metadata", None)
                self.breaker.success()
                return AIResult(
                    output,
                    self.name,
                    model,
                    latency,
                    getattr(usage, "prompt_token_count", None),
                    getattr(usage, "candidates_token_count", None),
                )
        self.breaker.failure()
        code = getattr(last, "code", None)
        raise AIUnavailable(f"{type(last).__name__}{f' {code}' if code else ''}")


def _retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    value = headers.get("retry-after") if hasattr(headers, "get") else None
    try:
        return min(float(value), 30.0) if value else None
    except ValueError:
        return None
