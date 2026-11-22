"""AI provider smoke test (Phase 2). Never prints an API key.

Run from the repo root:
    backend\\.venv\\Scripts\\python scripts\\ai_smoke.py            # provider from AI_PROVIDER in .env
    backend\\.venv\\Scripts\\python scripts\\ai_smoke.py openai     # or name it

Prints: whether the key is present and its length, which small models the key can use,
then makes ONE tiny structured call and reports model, valid JSON yes/no and latency.
OpenAI is a paid API: one call costs a small fraction of a cent.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
PROMPT = "Which country is Paris in? Answer with the city and the country."
SKIP_WORDS = (
    "audio",
    "realtime",
    "search",
    "transcribe",
    "tts",
    "image",
    "embedding",
    "codex",
)


class AiEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    ai_provider: str = "fake"
    openai_api_key: str = ""
    openai_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = ""


class Answer(BaseModel):
    city: str
    country: str


def status_of(exc: Exception) -> str:
    http = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)  # provider error code, e.g. "insufficient_quota"
    parts = [type(exc).__name__]
    if http:
        parts.append(f"HTTP {http}")
    if code and code != http:
        parts.append(f"code {code}")
    return " | ".join(parts)


def check_key(name: str, key: str) -> bool:
    if not key:
        print(f"{name}: missing. Save it with .\\scripts\\set-secret.ps1 {name}")
        return False
    print(f"{name}: present, length {len(key)}")
    return True


def run_openai(env: AiEnv) -> int:
    key = env.openai_api_key.strip()
    if not check_key("OPENAI_API_KEY", key):
        return 2
    from openai import OpenAI  # the only place this script imports the SDK

    client = OpenAI(api_key=key)
    try:
        ids = [m.id for m in client.models.list()]
    except Exception as exc:  # noqa: BLE001
        print(f"Listing models failed: {status_of(exc)}")
        return 1
    small = sorted(
        i
        for i in ids
        if i.startswith("gpt-") and "mini" in i and not any(w in i for w in SKIP_WORDS)
    )
    print(
        f"Small models this key can use ({len(small)}): {', '.join(small[:12]) or 'none'}"
    )
    model = env.openai_model or (small[-1] if small else "")
    if not model:
        print("No small model found to test. Set OPENAI_MODEL in .env.")
        return 1

    start = time.perf_counter()
    try:
        resp = client.responses.parse(model=model, input=PROMPT, text_format=Answer)
    except Exception as exc:  # noqa: BLE001
        print(f"Model: {model} | call failed: {status_of(exc)}")
        return 1
    latency_ms = round((time.perf_counter() - start) * 1000)
    parsed = getattr(resp, "output_parsed", None)
    valid = "yes" if isinstance(parsed, Answer) else "no"
    usage = getattr(resp, "usage", None)
    tokens = f"{usage.input_tokens} in / {usage.output_tokens} out" if usage else "n/a"
    print(
        f"Model: {model} | valid JSON: {valid} | latency: {latency_ms} ms | tokens: {tokens}"
    )
    return 0 if valid == "yes" else 1


def run_gemini(env: AiEnv) -> int:
    key = env.gemini_api_key.strip()
    if not check_key("GEMINI_API_KEY", key):
        return 2
    from google import genai  # the only place this script imports the SDK

    client = genai.Client(api_key=key)
    try:
        names = [
            m.name.removeprefix("models/")
            for m in client.models.list()
            if "generateContent" in (getattr(m, "supported_actions", None) or [])
            and "flash" in (m.name or "").lower()
        ]
    except Exception as exc:  # noqa: BLE001
        print(f"Listing models failed: {status_of(exc)}")
        return 1
    print(
        f"Flash models this key can use ({len(names)}): {', '.join(sorted(names)[:12]) or 'none'}"
    )
    model = env.gemini_model or next(
        (n for n in sorted(names, reverse=True) if "lite" not in n), ""
    )
    if not model:
        print("No Flash model available to test.")
        return 1

    start = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=model,
            contents=PROMPT,
            config={
                "response_mime_type": "application/json",
                "response_schema": Answer,
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Model: {model} | call failed: {status_of(exc)}")
        return 1
    latency_ms = round((time.perf_counter() - start) * 1000)
    try:
        Answer.model_validate_json(resp.text or "")
        valid = "yes"
    except Exception:  # noqa: BLE001
        valid = "no"
    print(f"Model: {model} | valid JSON: {valid} | latency: {latency_ms} ms")
    return 0 if valid == "yes" else 1


def main() -> int:
    env = AiEnv()
    provider = (sys.argv[1] if len(sys.argv) > 1 else env.ai_provider).lower()
    print(f"Provider: {provider}")
    if provider == "openai":
        return run_openai(env)
    if provider == "gemini":
        return run_gemini(env)
    print(
        "AI_PROVIDER is 'fake' (no real calls). Run with: scripts\\ai_smoke.py openai"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
