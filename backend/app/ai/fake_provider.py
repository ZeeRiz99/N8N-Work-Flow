"""FakeAIProvider: deterministic, offline and free, for tests, CI and an offline demo mode.

It reads the customer message from the prompt's data block and returns an AnalysisOutput whose
evidence quotes are real substrings of that message, so grounding and scoring run exactly as
they do with Gemini. Results are labelled provider "fake" everywhere they are shown.
"""

import re
import time

from app.ai.money import _AMOUNT
from app.ai.prompts.analysis_v1 import extract_message
from app.ai.provider import AIResult
from app.ai.schemas import AnalysisOutput

SPAM_HINTS = ("crypto", "seo services", "backlinks", "casino", "loan offer", "guest post")
JOB_HINTS = ("my cv", "my resume", "job opening", "hiring developers", "internship", "vacancy")
URGENT = [
    ("asap", "immediate"),
    ("urgent", "immediate"),
    ("this week", "immediate"),
    ("within a week", "immediate"),
    ("within a month", "soon"),
    ("next month", "soon"),
    ("soon", "soon"),
    ("no rush", "flexible"),
    ("next year", "flexible"),
]
INTENT_PHRASES = ["send a quote", "quote", "how much", "price", "proposal", "hire", "get started"]
SERVICE_WORDS = {
    "Website Development": ["website", "web site", "online ordering", "landing page", "shop"],
    "Booking System": ["booking", "appointment", "reservation"],
    "AI Chatbot": ["chatbot", "chat bot", "ai assistant"],
    "Automation Setup": ["automation", "automate", "workflow", "n8n", "zapier"],
}


def _find(text: str, phrase: str) -> str | None:
    """Return the phrase exactly as written in the text (keeps original casing)."""
    m = re.search(re.escape(phrase), text, re.IGNORECASE)
    return m.group(0) if m else None


class FakeAIProvider:
    name = "fake"
    model = "fake-v1"

    def analyze(self, system: str, user: str) -> AIResult:
        start = time.perf_counter()
        msg = extract_message(user)
        low = msg.lower()
        data: dict = {"extraction": {}, "assessment": {}}
        ex, assess = data["extraction"], data["assessment"]

        if sum(h in low for h in SPAM_HINTS) >= 1 and "http" in low:
            assess.update(intent="spam", summary="Looks like unsolicited marketing.")
            return self._result(data, start)
        if any(h in low for h in JOB_HINTS):
            assess.update(intent="job_seeker", summary="Someone looking for a job, not a client.")
            return self._result(data, start)

        services = []
        for name, words in SERVICE_WORDS.items():
            hit = next((q for w in words if (q := _find(msg, w))), None)
            if hit:
                services.append({"name": name, "evidence": hit})
        ex["service_interest"] = services[:3]

        money = _AMOUNT.search(msg)
        if money and (money.group(1) or money.group(3) or money.group(4)):
            ex["budget"] = {"evidence": money.group(0).strip(), "confidence": 0.7}
        for phrase, level in URGENT:
            q = _find(msg, phrase)
            if q:
                ex["timeline"] = {"text": phrase, "urgency": level, "evidence": q}
                break

        signals = [{"text": p, "evidence": q} for p in INTENT_PHRASES if (q := _find(msg, p))]
        assess["buying_signals"] = signals[:2]
        assess["intent"] = "hiring" if signals else ("researching" if services else "unknown")
        assess["summary"] = (
            f"Interested in {services[0]['name']}." if services else "General inquiry."
        )
        assess["recommended_next_action"] = "Reply with a short quote and two questions."
        return self._result(data, start)

    def _result(self, data: dict, start: float) -> AIResult:
        out = AnalysisOutput.model_validate(data)
        ms = round((time.perf_counter() - start) * 1000)
        return AIResult(out, self.name, self.model, ms, 0, 0)
