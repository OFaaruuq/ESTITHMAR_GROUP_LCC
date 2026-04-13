"""Shared input validation helpers."""

from __future__ import annotations

import re

# ITU E.164 maximum length; minimum practical length for a national / international subscriber number
_PHONE_DIGITS_MIN = 7
_PHONE_DIGITS_MAX = 15


def validate_phone(raw: str | None) -> tuple[str | None, str | None]:
    """
    Validate and normalize a phone number.

    Returns ``(normalized, None)`` on success. If ``raw`` is empty/whitespace,
    returns ``(None, None)`` (optional field). On failure returns ``(None, error_message)``.

    Normalization: leading ``+`` is kept for international numbers; otherwise digits only
    (spaces, hyphens, and parentheses are stripped).
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None

    if re.search(r"[A-Za-z]", s):
        return None, "Phone number must not contain letters."

    if not re.fullmatch(r"[\d+\-\s()./]+", s):
        return None, "Phone number may only contain digits and + ( ) - . / spaces."

    digits = re.sub(r"\D", "", s)
    if len(digits) < _PHONE_DIGITS_MIN or len(digits) > _PHONE_DIGITS_MAX:
        return None, (
            f"Phone number must contain between {_PHONE_DIGITS_MIN} and {_PHONE_DIGITS_MAX} digits "
            "(international format with country code is allowed)."
        )

    if s.startswith("+"):
        normalized = "+" + digits
    else:
        normalized = digits

    return normalized, None
