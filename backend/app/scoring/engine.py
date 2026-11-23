"""Deterministic, configurable, explainable lead scoring (master prompt §8.3, D12).

Seven factors, each a fraction 0..1 times its weight (weights sum to 100). Inputs are grounded
facts and the AI's assessment; the AI never sets a number. Overrides:
- spam intent caps the score at 10;
- disposable email or injection-flagged text sets needs_review and stops AI judgments
  (intent, urgency) from adding points;
- with no usable AI result the score is provisional, from code-extracted basics only.
"""

from dataclasses import dataclass, field

DEFAULT_WEIGHTS = {
    "budget_fit": 20,
    "buying_intent": 20,
    "urgency": 15,
    "service_relevance": 15,
    "completeness": 10,
    "engagement": 10,
    "business_fit": 10,
}
DEFAULT_THRESHOLDS = {"high_min": 80, "medium_min": 50}
LABELS = {
    "budget_fit": "Budget fit",
    "buying_intent": "Buying intent",
    "urgency": "Urgency",
    "service_relevance": "Service relevance",
    "completeness": "Completeness",
    "engagement": "Engagement",
    "business_fit": "Business fit",
}
INTENT_VALUE = {
    "hiring": 0.7,
    "price_check": 0.4,
    "partnership": 0.4,
    "researching": 0.3,
    "unknown": 0.2,
    "support_request": 0.1,
    "job_seeker": 0.0,
    "spam": 0.0,
}
# Calibrated so a clear buyer ("live within a month", budget in range, asks for a quote) lands in
# High, matching the master prompt's own example (§8.3: "+15 Urgency: within one month").
URGENCY_VALUE = {"immediate": 1.0, "soon": 0.9, "flexible": 0.5, "unspecified": 0.25}
DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "temp-mail.org",
    "yopmail.com",
    "trashmail.com",
    "sharklasers.com",
    "getnada.com",
    "dispostable.com",
}
NEUTRAL = 0.5


class ConfigError(ValueError):
    pass


def validate_config(weights: dict, thresholds: dict) -> None:
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ConfigError("Weights must cover exactly the seven factors.")
    if any((not isinstance(v, int)) or v < 0 for v in weights.values()):
        raise ConfigError("Each weight must be a whole number of 0 or more.")
    if sum(weights.values()) != 100:
        raise ConfigError(f"Weights must add up to 100 (now {sum(weights.values())}).")
    hi, med = thresholds.get("high_min"), thresholds.get("medium_min")
    if not (isinstance(hi, int) and isinstance(med, int) and 0 < med < hi <= 100):
        raise ConfigError("Bands need 0 < Medium start < High start <= 100.")


@dataclass
class ScoreInput:
    services: list[dict]  # grounded: {name, evidence, source}
    budget_min_minor: int | None
    budget_max_minor: int | None
    budget_comparable: bool  # same comparable currency as the catalog (ADR 006)
    budget_evidence: str | None
    intent: str
    urgency: str
    urgency_evidence: str | None
    buying_signals: list[dict]
    has_name: bool
    has_valid_email: bool
    has_phone: bool
    has_company: bool
    meaningful_message: bool
    has_timeline: bool
    inquiry_count: int
    email: str | None
    industry: str | None
    injection_flags: list[str] = field(default_factory=list)
    provisional: bool = False


@dataclass
class Factor:
    key: str
    points: int
    max: int
    reason: str
    evidence: str | None = None

    def as_dict(self) -> dict:
        return {
            "factor": self.key,
            "label": LABELS[self.key],
            "points": self.points,
            "max": self.max,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass
class ScoreResult:
    total: int
    band: str
    factors: list[Factor]
    needs_review: bool
    provisional: bool
    caps: list[str]
    explanation: str

    def breakdown(self) -> list[dict]:
        return [f.as_dict() for f in self.factors]


def _money(minor: int | None) -> str:
    return "?" if minor is None else f"${minor / 100:,.0f}"


def _budget(inp: ScoreInput, catalog: dict[str, dict]) -> tuple[float, str, str | None]:
    if inp.budget_max_minor is None and inp.budget_min_minor is None:
        return NEUTRAL, "Budget unknown; neutral share given.", None
    if not inp.budget_comparable:
        return (
            NEUTRAL,
            "Budget is in another currency or crypto; not compared.",
            inp.budget_evidence,
        )
    svc = next((catalog[s["name"]] for s in inp.services if s["name"] in catalog), None)
    if svc is None:
        return NEUTRAL, "No matching service to compare the budget with.", inp.budget_evidence
    budget = inp.budget_max_minor if inp.budget_max_minor is not None else inp.budget_min_minor
    lo, hi = svc.get("price_min_minor"), svc.get("price_max_minor")
    rng = f"{svc['name']} ({_money(lo)} to {_money(hi)})"
    if lo is None or budget >= lo:
        return 1.0, f"Budget of {_money(budget)} fits {rng}.", inp.budget_evidence
    if budget >= 0.7 * lo:
        return 0.6, f"Budget of {_money(budget)} is a little below {rng}.", inp.budget_evidence
    return 0.2, f"Budget of {_money(budget)} is far below {rng}.", inp.budget_evidence


def score(
    inp: ScoreInput,
    catalog: list[dict],
    weights: dict | None = None,
    thresholds: dict | None = None,
    ideal_customer: dict | None = None,
) -> ScoreResult:
    """catalog: [{"name", "price_min_minor", "price_max_minor"}]; ideal_customer may hold
    {"industries": [...], "min_budget_minor": int}."""
    weights = weights or DEFAULT_WEIGHTS
    thresholds = thresholds or DEFAULT_THRESHOLDS
    validate_config(weights, thresholds)
    by_name = {c["name"]: c for c in catalog}
    caps: list[str] = []

    domain = (inp.email or "").rsplit("@", 1)[-1].lower()
    disposable = domain in DISPOSABLE_DOMAINS
    distrust_ai = bool(inp.injection_flags) or disposable or inp.provisional
    if inp.injection_flags:
        caps.append("Message tried to instruct the AI; AI judgments were not used.")
    if disposable:
        caps.append("Throwaway email address; AI judgments were not used.")

    fractions: dict[str, tuple[float, str, str | None]] = {}
    fractions["budget_fit"] = _budget(inp, by_name)

    if distrust_ai:
        why = "provisional score" if inp.provisional else "needs review"
        fractions["buying_intent"] = (INTENT_VALUE["unknown"], f"Not judged ({why}).", None)
        fractions["urgency"] = (URGENCY_VALUE["unspecified"], f"Not judged ({why}).", None)
    else:
        signals = len(inp.buying_signals)
        intent_f = min(1.0, INTENT_VALUE.get(inp.intent, 0.2) + 0.15 * signals)
        sig_txt = f", {signals} buying signal{'s' if signals != 1 else ''}" if signals else ""
        first = inp.buying_signals[0]["evidence"] if signals else None
        fractions["buying_intent"] = (
            intent_f,
            f"{inp.intent.replace('_', ' ').capitalize()}{sig_txt}.",
            first,
        )
        fractions["urgency"] = (
            URGENCY_VALUE.get(inp.urgency, 0.25),
            f"Timeline: {inp.urgency}.",
            inp.urgency_evidence,
        )

    matched = [s for s in inp.services if s["name"] in by_name]
    if matched:
        fractions["service_relevance"] = (
            1.0,
            f"Matches {matched[0]['name']} in your services.",
            matched[0].get("evidence"),
        )
    elif inp.services:
        fractions["service_relevance"] = (
            0.25,
            "Asks for something outside your service list.",
            inp.services[0].get("evidence"),
        )
    else:
        fractions["service_relevance"] = (0.0, "No service mentioned.", None)

    checks = [
        inp.has_name,
        inp.has_valid_email,
        inp.has_phone,
        inp.has_company,
        inp.meaningful_message,
        inp.budget_max_minor is not None or inp.budget_min_minor is not None,
        inp.has_timeline,
    ]
    have = sum(checks)
    missing = [
        n
        for n, ok in zip(
            ["name", "email", "phone", "company", "message", "budget", "timeline"],
            checks,
            strict=True,
        )
        if not ok
    ]
    reason = f"{have} of 7 key details given." + (
        f" Missing: {', '.join(missing)}." if missing else ""
    )
    fractions["completeness"] = (have / 7, reason, None)

    repeat = max(0, inp.inquiry_count - 1)
    eng = min(1.0, 0.3 * min(repeat, 2) + (0.4 if inp.has_phone else 0.0))
    parts = []
    if repeat:
        parts.append(f"{repeat} follow-up message{'s' if repeat > 1 else ''}")
    if inp.has_phone:
        parts.append("phone given")
    fractions["engagement"] = (eng, ("; ".join(parts) or "First message, no phone") + ".", None)

    icp = ideal_customer or {}
    if not icp.get("industries") and not icp.get("min_budget_minor"):
        fractions["business_fit"] = (NEUTRAL, "No ideal-customer settings yet; neutral.", None)
    else:
        fit, notes = 0.0, []
        if icp.get("industries"):
            hit = inp.industry and any(i.lower() in inp.industry.lower() for i in icp["industries"])
            fit += 0.5 if hit else 0.0
            notes.append("industry matches" if hit else "industry not in your list")
        else:
            fit += 0.25
        if icp.get("min_budget_minor"):
            b = inp.budget_max_minor or inp.budget_min_minor
            ok = b is not None and inp.budget_comparable and b >= icp["min_budget_minor"]
            fit += 0.5 if ok else 0.0
            notes.append("budget meets your minimum" if ok else "budget below or unknown")
        else:
            fit += 0.25
        fractions["business_fit"] = (fit, "; ".join(notes).capitalize() + ".", None)

    factors = [
        Factor(k, round(fractions[k][0] * weights[k]), weights[k], fractions[k][1], fractions[k][2])
        for k in DEFAULT_WEIGHTS
    ]
    total = sum(f.points for f in factors)
    if inp.intent == "spam":  # applies even when the message also tried to steer the AI
        total = min(total, 10)
        caps.append("Looks like spam; score capped at 10.")
    total = max(0, min(100, total))
    band = (
        "high"
        if total >= thresholds["high_min"]
        else "medium"
        if total >= thresholds["medium_min"]
        else "low"
    )
    return ScoreResult(
        total,
        band,
        factors,
        distrust_ai and not inp.provisional,
        inp.provisional,
        caps,
        explain(total, band, factors, caps, inp.provisional),
    )


def explain(
    total: int, band: str, factors: list[Factor], caps: list[str], provisional: bool
) -> str:
    """Template explanation, e.g. "Score 86 · High. +20 Budget fit: ... −5 Completeness: ..."."""
    head = f"Score {total} · {band.capitalize()}{' (provisional)' if provisional else ''}."
    best = sorted(factors, key=lambda f: f.points, reverse=True)[:2]
    worst = sorted(factors, key=lambda f: f.points - f.max)[:1]
    parts = [f"+{f.points} {LABELS[f.key]}: {f.reason}" for f in best if f.points > 0]
    parts += [
        f"−{f.max - f.points} {LABELS[f.key]}: {f.reason}"
        for f in worst
        if f.max - f.points > 0 and f not in best
    ]
    return " ".join([head, *parts, *caps])
