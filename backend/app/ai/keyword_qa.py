"""Keyword answer over a lead's records. Used by the offline provider and as the fallback when
the AI is unavailable: it finds the records that mention the question's words and cites them."""

import re

from app.ai.schemas import QAOutput

STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "what",
    "did",
    "does",
    "do",
    "how",
    "when",
    "who",
    "they",
    "their",
    "this",
    "lead",
    "of",
    "for",
    "to",
    "in",
    "on",
    "and",
    "or",
    "about",
    "any",
    "has",
    "have",
    "it",
    "we",
    "i",
    "you",
    "with",
    "much",
    "many",
    "which",
}
OFF_TOPIC = re.compile(
    r"\b(weather|write (me )?(a |some )?(code|poem|story)|other leads|all leads|system prompt|"
    r"send (an? )?email|delete|ignore (all|previous))\b",
    re.IGNORECASE,
)
SYNONYMS = {
    "budget": ["$", "budget", "usd", "pkr", "eur"],
    "phone": ["phone", "+"],
    "when": ["month", "week", "asap", "soon"],
    "deadline": ["month", "week", "asap"],
}


def _text(record: dict) -> str:
    return " ".join(str(v) for k, v in record.items() if k != "id").lower()


def keyword_answer(question: str, records: dict) -> QAOutput:
    if OFF_TOPIC.search(question):
        return QAOutput(
            answer="I can only answer questions about this lead's own records.", refused=True
        )
    raw = re.findall(r"[a-z0-9$]+", question.lower())
    terms = {w for w in raw if w not in STOP}
    for w in raw:  # synonyms first: "when" is a stop word but means "timeline"
        terms.update(SYNONYMS.get(w, []))
    hits = []
    for group in ("inquiries", "notes", "activities", "analysis"):
        for rec in records.get(group, []):
            text = _text(rec)
            if any(t in text for t in terms):
                hits.append(rec)
    if not hits:
        return QAOutput(answer="The records for this lead do not mention that.", citations=[])
    lines = []
    for rec in hits[:3]:
        snippet = next(
            (str(rec[k]) for k in ("message", "body", "summary", "text", "type") if rec.get(k)), ""
        )
        lines.append(f"- {snippet[:160]}")
    return QAOutput(
        answer="Records that mention it:\n" + "\n".join(lines),
        citations=[r["id"] for r in hits[:5]],
    )
