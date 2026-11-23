"""Code checks on every reply draft (master prompt §8.4, ADR 010). The model writes; code decides
whether the draft is safe to send. Results are shown to the approver and rerun on every edit.

Each check: {"key", "label", "ok", "severity": "fail"|"warn", "detail"}.
"""

import re
from urllib.parse import urlparse

from app.ai.money import _AMOUNT, _to_number

MAX_SUBJECT_CHARS = 90
MAX_BODY_WORDS = 250
OPT_OUT_LINE = 'If you\'d rather not hear from us again, just reply "unsubscribe".'

_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>()\"']+", re.IGNORECASE)
_PROMISES = [
    (
        r"\b(\d{1,3}\s?%\s?off|discount|coupon|promo code|free of charge|for free|no charge)\b",
        "a discount or free work",
    ),
    (r"\b(attached|attachment|i've attached|please find)\b", "an attachment"),
    (r"\b(guarantee[ds]?|100% satisfaction)\b", "a guarantee"),
    (
        r"\b(on|this|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        "a specific day",
    ),
    (r"\b(tomorrow|tonight)\b", "a specific day"),
    (r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b", "a specific time"),
    (r"\b(i have|we have|i've|we've)\s+(booked|scheduled|set up)\b", "a booked meeting"),
    (r"\b(deliver|launch|finish|done|ready)\w*\s+(by|within|in)\s+\d", "a delivery date"),
]
_PROMISES_RX = [(re.compile(p, re.IGNORECASE), what) for p, what in _PROMISES]


def _check(key, label, ok, detail="", severity="fail") -> dict:
    return {"key": key, "label": label, "ok": bool(ok), "severity": severity, "detail": detail}


def _amounts(text: str) -> list[float]:
    out = []
    for m in _AMOUNT.finditer(text):
        if m.group(1) or m.group(3) or m.group(4):  # has a currency or multiplier
            out.append(_to_number(m.group(2), m.group(3)))
    return out


def run_checks(
    subject: str,
    body: str,
    services_mentioned: list[str],
    catalog: list[dict],
    allowed_domains: set[str],
    do_not_contact: bool,
    has_email: bool,
    language: str = "en",
) -> list[dict]:
    names = {c["name"] for c in catalog}
    text = f"{subject}\n{body}"
    checks = []

    unknown = [s for s in services_mentioned if s not in names]
    checks.append(
        _check(
            "services",
            "Services are on your service list",
            not unknown,
            f"Not on the list: {', '.join(unknown)}" if unknown else "",
        )
    )

    allowed_prices = set()
    for c in catalog:
        for v in (c.get("price_min_minor"), c.get("price_max_minor")):
            if v is not None:
                allowed_prices.add(round(v / 100, 2))
    bad = sorted({a for a in _amounts(text) if round(a, 2) not in allowed_prices})
    checks.append(
        _check(
            "prices",
            "Prices match the service list",
            not bad,
            f"Amounts not on the price list: {', '.join(f'{a:g}' for a in bad)}" if bad else "",
        )
    )

    links = [u for u in _URL.findall(text)]
    outside = []
    for u in links:
        host = urlparse(u if "://" in u else f"http://{u}").hostname or ""
        host = host.removeprefix("www.")
        if not any(host == d or host.endswith(f".{d}") for d in allowed_domains):
            outside.append(host or u)
    checks.append(
        _check(
            "links",
            "No links outside the allow-list",
            not outside,
            f"Links to: {', '.join(outside)}" if outside else "",
        )
    )

    promised = sorted({what for rx, what in _PROMISES_RX if rx.search(text)})
    checks.append(
        _check(
            "promises",
            "No promised dates, meetings or discounts",
            not promised,
            f"Mentions {', '.join(promised)}" if promised else "",
        )
    )

    words = len(body.split())
    checks.append(
        _check(
            "length",
            "Length within limits",
            len(subject) <= MAX_SUBJECT_CHARS and words <= MAX_BODY_WORDS,
            f"Subject {len(subject)}/{MAX_SUBJECT_CHARS} characters, body "
            f"{words}/{MAX_BODY_WORDS} words",
        )
    )

    checks.append(_check("opt_out", "Opt-out line added", OPT_OUT_LINE in body))
    checks.append(
        _check(
            "contactable",
            "Not on the do-not-contact list, has an email",
            not do_not_contact and has_email,
            "Marked do not contact"
            if do_not_contact
            else ("No email address" if not has_email else ""),
        )
    )
    checks.append(
        _check(
            "language",
            "Reply language",
            language in ("en", "ur"),
            ""
            if language in ("en", "ur")
            else f"Customer wrote in '{language}'; the reply is in English, please check",
            severity="warn",
        )
    )
    return checks


def finalize_body(body: str) -> str:
    """Strip anything the model must not control, then append the opt-out line in code."""
    body = body.replace(OPT_OUT_LINE, "").rstrip()
    return f"{body}\n\n{OPT_OUT_LINE}"


def passed(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks if c["severity"] == "fail")
