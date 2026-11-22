"""Key hashing and comparison. Keys are stored as SHA-256 hashes, never in plain text."""

import hashlib
import hmac
import secrets


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def keys_match(presented: str, expected: str) -> bool:
    """Constant-time comparison of two secrets."""
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def new_public_form_key() -> str:
    return "pk_" + secrets.token_urlsafe(24)


def key_prefix(key: str) -> str:
    """The first characters of a key, safe to show and log."""
    return key[:8]
