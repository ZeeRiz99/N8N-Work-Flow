"""Grounding (master prompt §8.2): keep only facts the customer actually wrote.

A fact survives only if its evidence quote appears in the inquiry (case- and whitespace-
insensitive). Budget numbers are re-parsed from the quote by code; when the model's number
disagrees, the quote wins. Structured form choices are trusted facts with source "form".
Everything rejected is listed, which the evaluation harness turns into a rejection rate.
"""

import re
from dataclasses import dataclass, field

from app.ai.money import Money, parse_budget_band, parse_money
from app.ai.schemas import AnalysisOutput

FORM_TIMELINE_URGENCY = {
    "within 1 month": "soon",
    "within a month": "soon",
    "1 to 3 months": "flexible",
    "no fixed date": "flexible",
}


@dataclass
class Grounded:
    services: list[dict] = field(default_factory=list)  # {name, evidence, source}
    budget: Money | None = None
    budget_evidence: str | None = None
    budget_source: str | None = None  # "message" | "form"
    timeline_text: str | None = None
    urgency: str = "unspecified"
    timeline_evidence: str | None = None
    timeline_source: str | None = None
    company: str | None = None
    industry: str | None = None
    requirements: list[dict] = field(default_factory=list)
    buying_signals: list[dict] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # {field, reason}
    conflicts: list[str] = field(default_factory=list)
    accepted: int = 0

    def as_dict(self) -> dict:
        b = self.budget
        return {
            "services": self.services,
            "budget": None
            if b is None
            else {
                "min_minor": b.min_minor,
                "max_minor": b.max_minor,
                "currency": b.currency,
                "comparable": b.comparable_currency is not None,
                "evidence": self.budget_evidence,
                "source": self.budget_source,
            },
            "timeline": {
                "text": self.timeline_text,
                "urgency": self.urgency,
                "evidence": self.timeline_evidence,
                "source": self.timeline_source,
            },
            "company": self.company,
            "industry": self.industry,
            "requirements": self.requirements,
            "buying_signals": self.buying_signals,
            "missing_info": self.missing_info,
            "rejected": self.rejected,
            "conflicts": self.conflicts,
        }


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def quoted(evidence: str | None, source_text: str) -> bool:
    """True when `evidence` is a real (non-trivial) quote from the source text."""
    if not evidence:
        return False
    e = _norm(evidence).strip(" .,!?\"'")
    return len(e) >= 2 and e in _norm(source_text)


def ground(
    out: AnalysisOutput,
    message: str,
    form_fields: dict | None,
    catalog: list[dict],
    org_currency: str = "USD",
) -> Grounded:
    """catalog: [{"name": str, "keywords": [str]}] for the organization's active services."""
    g = Grounded()
    form = form_fields or {}
    ex, assess = out.extraction, out.assessment
    names = {c["name"].lower(): c["name"] for c in catalog}

    def reject(field_name: str, reason: str) -> None:
        g.rejected.append({"field": field_name, "reason": reason})

    # --- services
    for mention in ex.service_interest:
        if not quoted(mention.evidence, message):
            reject("service_interest", "quote not found in the message")
            continue
        name = names.get(mention.name.lower())
        if name is None:
            # Not a catalog name: maybe the quote contains a catalog keyword.
            for c in catalog:
                if any(k and k.lower() in _norm(mention.evidence) for k in c.get("keywords", [])):
                    name = c["name"]
                    break
        g.services.append(
            {"name": name or "other", "evidence": mention.evidence, "source": "message"}
        )
        g.accepted += 1
    form_service = names.get(str(form.get("service", "")).lower())
    if form_service and form_service not in {s["name"] for s in g.services}:
        g.services.insert(0, {"name": form_service, "evidence": None, "source": "form"})
    # Deduplicate, keep order.
    seen: set[str] = set()
    g.services = [s for s in g.services if not (s["name"] in seen or seen.add(s["name"]))]

    # --- budget: the quote is the truth; the model's number is only a hint.
    b = ex.budget
    if b.evidence or b.min_amount is not None or b.max_amount is not None:
        if not quoted(b.evidence, message):
            reject("budget", "quote not found in the message")
        else:
            parsed = parse_money(b.evidence, default_currency=org_currency)
            if parsed is None:
                reject("budget", "quote contains no amount")
            else:
                model_hi = b.max_amount or b.min_amount
                parsed_hi = (parsed.max_minor or 0) / 100
                if (
                    model_hi is not None
                    and parsed_hi
                    and abs(model_hi - parsed_hi) > 0.01 * parsed_hi
                ):
                    g.conflicts.append(
                        "budget: model number differed from the quote; used the quote"
                    )
                g.budget, g.budget_evidence, g.budget_source = parsed, b.evidence, "message"
                g.accepted += 1
    band = parse_budget_band(form.get("budget"), org_currency)
    if band is not None:
        if g.budget is None:
            g.budget, g.budget_source = band, "form"
            g.budget_evidence = None
        elif g.budget.comparable_currency == band.comparable_currency:
            hi = g.budget.max_minor or 0
            outside = (band.min_minor and hi < band.min_minor) or (
                band.max_minor and hi > band.max_minor
            )
            if outside:
                g.conflicts.append("budget: the message and the form budget band disagree")

    # --- timeline
    t = ex.timeline
    if t.evidence or t.text:
        if quoted(t.evidence, message):
            g.timeline_text, g.urgency, g.timeline_evidence = t.text, t.urgency, t.evidence
            g.timeline_source = "message"
            g.accepted += 1
        else:
            reject("timeline", "quote not found in the message")
    form_tl = str(form.get("timeline", "")).strip()
    if form_tl and g.timeline_source is None:
        g.timeline_text, g.timeline_source = form_tl, "form"
        g.urgency = FORM_TIMELINE_URGENCY.get(form_tl.lower(), "unspecified")

    # --- simple text facts
    for attr, fact in (("company", ex.company), ("industry", ex.industry)):
        if fact.value:
            # Industry is an inference ("bakery" -> food retail); its quote must still exist.
            if quoted(fact.evidence, message):
                setattr(g, attr, fact.value)
                g.accepted += 1
            else:
                reject(attr, "quote not found in the message")

    for item in ex.requirements:
        if quoted(item.evidence, message):
            g.requirements.append({"text": item.text, "evidence": item.evidence})
            g.accepted += 1
        else:
            reject("requirements", "quote not found in the message")
    for item in assess.buying_signals:
        if quoted(item.evidence, message):
            g.buying_signals.append({"text": item.text, "evidence": item.evidence})
            g.accepted += 1
        else:
            reject("buying_signals", "quote not found in the message")

    # --- missing info: the model's list, plus anything we could not ground.
    missing = [m for m in assess.missing_info if m]
    if g.budget is None and "budget" not in " ".join(missing).lower():
        missing.append("budget")
    if g.timeline_source is None and "timeline" not in " ".join(missing).lower():
        missing.append("timeline")
    g.missing_info = missing[:10]
    return g
