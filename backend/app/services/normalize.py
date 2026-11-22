"""Normalization rules (master prompt §6): email lowercased and trimmed; phone to E.164."""

import phonenumbers


def normalize_email(email: str | None) -> str | None:
    """Lowercase and trim. Gmail dots are kept on purpose."""
    if not email:
        return None
    e = email.strip().lower()
    return e or None


def normalize_phone(raw: str | None, default_region: str = "US") -> str | None:
    """E.164 (+14155550123) when the number is valid, else None (raw is still kept)."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw, (default_region or "US").upper())
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
