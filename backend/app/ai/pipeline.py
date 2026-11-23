"""The pure (database-free) steps of lead analysis, shared by the service and the eval harness,
so the evaluation measures exactly the code that runs in production.

prepare(): guard the text and build the prompt and its cache hash.
assess():  ground the model output (or nothing, when the AI did not run) and score it.
"""

import hashlib
from dataclasses import dataclass

from app.ai.grounding import Grounded, ground
from app.ai.guard import GuardResult, screen
from app.ai.prompts import analysis_v1 as prompt
from app.ai.schemas import AnalysisOutput
from app.scoring.engine import ScoreInput, ScoreResult, score


@dataclass(frozen=True)
class Prepared:
    guard: GuardResult
    user_prompt: str
    input_hash: str

    @property
    def has_text(self) -> bool:
        return bool(self.guard.text.strip())


@dataclass(frozen=True)
class LeadFacts:
    full_name: str | None
    email: str | None
    phone: str | None
    company: str | None
    inquiry_count: int = 1


@dataclass(frozen=True)
class Assessed:
    grounded: Grounded
    score_input: ScoreInput
    result: ScoreResult
    needs_review: bool


def prepare(message: str | None, form: dict, catalog: list[dict], org_name: str) -> Prepared:
    guard = screen(message or "")
    user = prompt.build_user(guard.text, form, [c["name"] for c in catalog], org_name)
    digest = hashlib.sha256(f"{prompt.PROMPT_VERSION}\n{prompt.SYSTEM}\n{user}".encode())
    return Prepared(guard, user, digest.hexdigest())


def comparable(currency: str) -> str:
    return "USD" if currency in {"USD", "USDT", "USDC"} else currency


def assess(
    output: AnalysisOutput | None,
    prep: Prepared,
    form: dict,
    catalog: list[dict],
    org_currency: str,
    lead: LeadFacts,
    weights: dict | None = None,
    thresholds: dict | None = None,
    ideal_customer: dict | None = None,
) -> Assessed:
    text = prep.guard.text
    # No usable model output: only trusted form choices count.
    grounded = ground(
        output or AnalysisOutput(),
        text if output else "",
        form,
        catalog if output else [],
        org_currency,
    )
    b = grounded.budget
    inp = ScoreInput(
        services=grounded.services,
        budget_min_minor=b.min_minor if b else None,
        budget_max_minor=b.max_minor if b else None,
        budget_comparable=bool(b and b.comparable_currency == comparable(org_currency)),
        budget_evidence=grounded.budget_evidence,
        intent=output.assessment.intent if output else "unknown",
        urgency=grounded.urgency,
        urgency_evidence=grounded.timeline_evidence,
        buying_signals=grounded.buying_signals,
        has_name=bool(lead.full_name and lead.full_name.strip()),
        has_valid_email=bool(lead.email and "@" in lead.email),
        has_phone=bool(lead.phone),
        has_company=bool(lead.company or grounded.company),
        meaningful_message=len(text.split()) >= 8,
        has_timeline=grounded.timeline_source is not None,
        inquiry_count=lead.inquiry_count,
        email=lead.email,
        industry=grounded.industry,
        injection_flags=prep.guard.flags,
        provisional=output is None,
    )
    res = score(inp, catalog, weights, thresholds, ideal_customer)
    return Assessed(grounded, inp, res, res.needs_review or prep.guard.needs_review)
