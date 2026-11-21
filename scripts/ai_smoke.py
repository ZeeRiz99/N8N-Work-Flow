"""Gemini smoke test (Phase 2). Never prints the API key.

Run from the repo root:
    backend\\.venv\\Scripts\\python scripts\\ai_smoke.py

Prints: whether the key is present and its length, which Flash models the key can use,
then makes ONE tiny structured call and reports model, valid JSON yes/no and latency.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class AiEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    gemini_api_key: str = ""
    gemini_model: str = ""


class Answer(BaseModel):
    city: str
    country: str


def status_of(exc: Exception) -> str:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return f"{type(exc).__name__} (HTTP {code})" if code else type(exc).__name__


def main() -> int:
    env = AiEnv()
    key = env.gemini_api_key.strip()
    if not key:
        print("GEMINI_API_KEY: missing. Type it into .env yourself, then run this again.")
        return 2
    print(f"GEMINI_API_KEY: present, length {len(key)}")

    from google import genai  # imported only here: the one place this script needs the SDK

    client = genai.Client(api_key=key)

    try:
        names = []
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if "generateContent" in actions and "flash" in (m.name or "").lower():
                names.append(m.name.removeprefix("models/"))
    except Exception as exc:  # noqa: BLE001
        print(f"Listing models failed: {status_of(exc)}")
        return 1
    print(f"Flash models this key can use ({len(names)}): {', '.join(sorted(names)[:12]) or 'none'}")

    model = env.gemini_model or next((n for n in sorted(names, reverse=True) if "lite" not in n), "")
    if not model:
        print("No Flash model available to test.")
        return 1

    start = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=model,
            contents="Which country is Paris in? Answer with the city and the country.",
            config={"response_mime_type": "application/json", "response_schema": Answer},
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


if __name__ == "__main__":
    sys.exit(main())
