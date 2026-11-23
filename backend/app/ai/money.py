"""Money parsing for budgets written by people: "$2,000", "2k", "$2,000-3,000", "PKR 3 lakh",
"around 1.5k USD", "2000 USDT". Returns integer minor units (D17), never floats or strings.

Stablecoins (USDT, USDC) count as USD 1:1. Volatile crypto keeps its own code and is marked
not comparable (ADR 006).
"""

import re
from dataclasses import dataclass

STABLECOINS = {"USDT", "USDC"}
CRYPTO = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"}
CURRENCY_WORDS = {
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "usdt": "USDT",
    "usdc": "USDC",
    "pkr": "PKR",
    "rs": "PKR",
    "rs.": "PKR",
    "rupees": "PKR",
    "rupee": "PKR",
    "rupay": "PKR",
    "rupaye": "PKR",
    "rupiya": "PKR",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "pounds": "GBP",
    "aed": "AED",
    "sar": "SAR",
    "inr": "INR",
    "cad": "CAD",
    "aud": "AUD",
    "btc": "BTC",
    "bitcoin": "BTC",
    "eth": "ETH",
    "ether": "ETH",
    "sol": "SOL",
}
MULTIPLIERS = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "lakh": 100_000,
    "lac": 100_000,
    "lakhs": 100_000,
    "crore": 10_000_000,
}

# 2,000 / 2 000 / 4.000 (European grouping: dot followed by exactly three digits) / 2.5
_NUM = r"(\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+(?![\d.])|\d+(?:\.\d+)?)"
_EURO_GROUPED = re.compile(r"\d{1,3}(?:\.\d{3})+")
SOUTH_ASIAN = {"lakh", "lac", "lakhs", "crore"}
_MULT = r"(k|thousand|m|million|lakhs?|lac|crore)?"
# Word currencies must stand alone: "years 2000" is not "rs 2000", "2000 solutions" is not SOL.
_CUR = (
    r"(?<![a-z])(\$|us\$|usdt|usdc|usd|dollars?|pkr|rs\.?|rupees?|rupaye?|rupiya|€|eur|euros?"
    r"|£|gbp|pounds|aed|sar|inr|cad|aud|btc|bitcoin|eth|ether|sol)(?![a-z])"
)
_AMOUNT = re.compile(rf"(?:{_CUR}\s*)?{_NUM}\s*{_MULT}\b\s*(?:{_CUR})?", re.IGNORECASE)
_RANGE_SEP = re.compile(r"\s*(?:-|–|—|to|and)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Money:
    min_minor: int | None
    max_minor: int | None
    currency: str | None  # ISO-like code; None when the text gave no currency

    @property
    def comparable_currency(self) -> str | None:
        """The currency used for comparison: stablecoins become USD; volatile crypto None."""
        if self.currency in STABLECOINS:
            return "USD"
        if self.currency in CRYPTO:
            return None
        return self.currency


def _to_number(num: str, mult: str | None) -> float:
    if _EURO_GROUPED.fullmatch(num):
        num = num.replace(".", "")
    value = float(re.sub(r"[,\s]", "", num))
    if mult:
        value *= MULTIPLIERS[mult.lower()]
    return value


def _minor(value: float, currency: str | None) -> int:
    # Crypto amounts are kept in 1e-8 units so 0.05 BTC stays exact enough; fiat uses cents.
    scale = 100_000_000 if currency in CRYPTO else 100
    return round(value * scale)


def parse_money(
    text: str | None, default_currency: str | None = None, strict: bool = False
) -> Money | None:
    """Parse the first budget-like amount or range in `text`. None if there is none.

    strict=True (used when guessing from free text without the AI) requires a currency or a
    multiplier, so "live by 2026" or "50 products" is never read as a budget.
    """
    if not text:
        return None
    found = list(_AMOUNT.finditer(text))

    def unit(m: re.Match) -> bool:
        return bool(m.group(1) or m.group(3) or m.group(4))

    def joined(a: re.Match, b: re.Match) -> bool:
        between = text[a.end() : b.start()]
        return bool(_RANGE_SEP.fullmatch(between)) or between.strip() in ("", "-", "–")

    def usable(i: int) -> bool:
        m = found[i]
        if unit(m):
            return True
        # "2-3k": a bare number that starts a range whose other end has the unit.
        if i + 1 < len(found) and joined(m, found[i + 1]) and unit(found[i + 1]):
            return True
        return not strict and _to_number(m.group(2), None) >= 100  # "2 pages" is no budget

    start = next((i for i in range(len(found)) if usable(i)), None)
    if start is None:
        return None
    matches = found[start:]
    first = matches[0]
    cur = first.group(1) or first.group(4)
    amounts = [(first.group(2), first.group(3))]
    # A range: "2,000-3,000", "$2k to $3k", "between 2000 and 3000".
    if len(matches) > 1:
        between = text[first.end() : matches[1].start()]
        if _RANGE_SEP.fullmatch(between) or between.strip() in ("", "-", "–"):
            second = matches[1]
            cur = cur or second.group(1) or second.group(4)
            amounts.append((second.group(2), second.group(3)))
            # "2-3k": the multiplier on the second number applies to both.
            if amounts[1][1] and not amounts[0][1]:
                amounts[0] = (amounts[0][0], amounts[1][1])
    mults = {(m or "").lower() for _, m in amounts}
    if cur:
        currency = CURRENCY_WORDS.get(cur.lower(), None)
    elif mults & SOUTH_ASIAN:
        # "3 lakh" with no currency word is rupees, never dollars.
        currency = "INR" if default_currency == "INR" else "PKR"
    else:
        currency = default_currency
    values = [_to_number(n, m) for n, m in amounts]
    # Bare small numbers without currency or multiplier ("3 pages", "2 weeks") are not budgets.
    if not cur and not any(m for _, m in amounts) and max(values) < 100:
        return None
    lo, hi = min(values), max(values)
    return Money(_minor(lo, currency), _minor(hi, currency), currency)


def parse_budget_band(band: str | None, default_currency: str = "USD") -> Money | None:
    """The public form's budget choices: "Under $500", "$1,500 to $5,000", "Over $5,000"."""
    if not band or band.lower().startswith("not sure"):
        return None
    m = parse_money(band, default_currency)
    if m is None:
        return None
    low = band.lower()
    if low.startswith("under") or low.startswith("below"):
        return Money(0, m.max_minor, m.currency)
    if low.startswith("over") or low.startswith("above"):
        return Money(m.min_minor, None, m.currency)
    return m
