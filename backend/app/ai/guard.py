"""Input guard (master prompt §8.6). Customer text is hostile by default.

The guard never decides alone: it strips invisible characters, truncates, and flags text that
looks like an attempt to instruct the model. Flagged leads get `needs_review`, and the scoring
engine refuses to let AI judgments raise their score.
"""

import re
import unicodedata
from dataclasses import dataclass, field

MAX_CHARS = 4000

# Zero-width and bidirectional control characters are used to hide instructions.
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")

INJECTION_PATTERNS = [
    (r"\bignore\b.{0,40}\b(instructions?|rules|prompt|above|previous)\b", "ignore_instructions"),
    (r"\bdisregard\b.{0,40}\b(instructions?|rules|above|previous)\b", "ignore_instructions"),
    (r"\bforget\b.{0,30}\b(instructions?|rules|everything)\b", "ignore_instructions"),
    (r"\bsystem\s*prompt\b|\bdeveloper\s*mode\b|\bjailbreak\b", "system_prompt"),
    (r"\byou\s+are\s+now\b|\bact\s+as\s+(an?\s+)?(ai|assistant|admin|system)\b", "role_play"),
    (r"\b(new|updated)\s+instructions?\b", "ignore_instructions"),
    (
        r"\b(give|set|assign|rate|score)\b.{0,30}\b(score|priority|rating)\b.{0,20}"
        r"\b(100|max(imum)?|high(est)?|top)\b",
        "score_manipulation",
    ),
    (
        r"\b(mark|classify|label)\b.{0,20}\b(as\s+)?(high|urgent|priority|vip)\b",
        "score_manipulation",
    ),
    (
        r"\b(reveal|print|show|repeat|leak)\b.{0,40}\b(prompt|instructions|api\s*key|secret|"
        r"password|token|other\s+(leads|customers))\b",
        "exfiltration",
    ),
    (r"<\s*/?\s*(system|assistant|instructions?)\s*>|\[\s*(system|inst)\s*\]", "fake_markup"),
    (r"\b(send|email|forward)\b.{0,40}\b(to|at)\b.{0,40}@", "action_request"),
    (
        r"\b(rate|give|set|assign|make)\b.{0,30}\b(max(imum)?|highest|top)\b.{0,15}"
        r"\b(priority|score|rating)\b",
        "score_manipulation",
    ),
    (
        r"\b(note|message|instructions?)\s+(to|for)\s+the\s+(ai|assistant|model|bot|llm)\b",
        "addresses_the_model",
    ),
    # Text shaped like our output schema: an attempt to pre-fill the model's answer.
    (
        r"\"(assessment|extraction|intent|buying_signals|service_interest|score|priority)\"\s*:",
        "schema_injection",
    ),
    # A bracketed note about "the customer" posing as a system annotation.
    (r"\[[^\]]{0,200}\bthe\s+(customer|lead|client)('s)?\b[^\]]{0,200}\]", "fake_annotation"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE | re.DOTALL), name) for p, name in INJECTION_PATTERNS]


@dataclass
class GuardResult:
    text: str
    truncated: bool = False
    invisible_removed: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.flags) or self.invisible_removed > 0


def screen(raw: str | None) -> GuardResult:
    text = unicodedata.normalize("NFKC", raw or "")
    cleaned, removed = _INVISIBLE.subn("", text)
    truncated = len(cleaned) > MAX_CHARS
    if truncated:
        cleaned = cleaned[:MAX_CHARS]
    flags = sorted({name for rx, name in _COMPILED if rx.search(cleaned)})
    if removed:
        flags.append("hidden_characters")
    return GuardResult(cleaned, truncated, removed, flags)
