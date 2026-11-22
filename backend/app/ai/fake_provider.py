"""FakeAIProvider (P3): deterministic, offline, free. Clearly labelled "fake" wherever shown.

It stands in for the real provider (P5) so the whole pipeline can be built and tested first.
The score here is a crude keyword heuristic, NOT the real scoring engine (master prompt §8.3).
"""

import re
from dataclasses import dataclass

SPAM_HINTS = ("crypto", "seo services", "backlinks", "casino", "loan offer", "http://", "https://")
BUDGET_RE = re.compile(r"(\$|usd|usdt|usdc|pkr|€|£)\s?\d|\d\s?(k|000)\b", re.IGNORECASE)
URGENT_WORDS = (
    "asap",
    "urgent",
    "this week",
    "within a month",
    "within a week",
    "soon",
    "deadline",
)
INTENT_WORDS = ("quote", "price", "proposal", "hire", "start", "budget", "cost")


@dataclass(frozen=True)
class FakeAnalysis:
    score: int
    band: str
    summary: str


def band_for(score: int, high_min: int = 80, medium_min: int = 50) -> str:
    if score >= high_min:
        return "high"
    if score >= medium_min:
        return "medium"
    return "low"


def analyze(message: str, has_phone: bool, has_company: bool, form_fields: dict) -> FakeAnalysis:
    text = message.lower()
    if sum(hint in text for hint in SPAM_HINTS) >= 2:
        return FakeAnalysis(5, "low", "Looks like spam (fake analysis).")

    score = 30
    if BUDGET_RE.search(text) or form_fields.get("budget"):
        score += 20
    if any(w in text for w in INTENT_WORDS):
        score += 20
    if any(w in text for w in URGENT_WORDS) or form_fields.get("timeline", "").startswith("Within"):
        score += 15
    if form_fields.get("service"):
        score += 5
    if has_phone:
        score += 5
    if has_company:
        score += 5
    score = min(score, 100)
    band = band_for(score)
    return FakeAnalysis(score, band, f"Fake analysis: scored {score} ({band}) from keywords only.")
