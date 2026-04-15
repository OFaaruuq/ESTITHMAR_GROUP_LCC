"""Share purchase rules for new subscriptions (whole shares only).

Defaults are defined below; admins can override unit price and min/max share counts
in System settings (stored in ``AppSettings.extra_json``).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Code fallbacks when settings are missing or invalid.
SHARE_UNIT_PRICE = Decimal("30")
MIN_SHARE_UNITS = 36
MAX_SHARE_UNITS = 100_000


def _settings_extra() -> dict:
    try:
        from estithmar.models import get_or_create_settings

        return get_or_create_settings().get_extra()
    except Exception:
        return {}


def effective_share_unit_price() -> Decimal:
    ex = _settings_extra()
    raw = ex.get("share_unit_price")
    if raw is None or raw == "":
        return SHARE_UNIT_PRICE
    try:
        d = Decimal(str(raw).strip().replace(",", ""))
        if d <= 0:
            return SHARE_UNIT_PRICE
        return d.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return SHARE_UNIT_PRICE


def effective_min_share_units() -> int:
    ex = _settings_extra()
    raw = ex.get("min_share_units")
    if raw is None or raw == "":
        return MIN_SHARE_UNITS
    try:
        n = int(raw)
        return max(1, min(n, 9_999_999))
    except (TypeError, ValueError):
        return MIN_SHARE_UNITS


def effective_max_share_units() -> int:
    ex = _settings_extra()
    raw = ex.get("max_share_units")
    if raw is None or raw == "":
        return MAX_SHARE_UNITS
    try:
        n = int(raw)
        return max(1, min(n, 99_999_999))
    except (TypeError, ValueError):
        return MAX_SHARE_UNITS


def min_subscribed_amount() -> Decimal:
    unit = effective_share_unit_price()
    return unit * effective_min_share_units()


def max_subscribed_amount() -> Decimal:
    unit = effective_share_unit_price()
    return unit * effective_max_share_units()


def resolve_share_subscription_amounts(*, share_units: int | None) -> tuple[Decimal, Decimal, Decimal]:
    """Return (subscribed_amount, share_unit_price, share_units_subscribed) for a valid purchase."""
    min_u = effective_min_share_units()
    max_u = effective_max_share_units()
    if min_u > max_u:
        min_u, max_u = max_u, min_u
    unit = effective_share_unit_price()
    if share_units is None:
        raise ValueError("Number of shares is required.")
    if share_units < min_u or share_units > max_u:
        raise ValueError(
            f"Number of shares must be between {min_u:,} and {max_u:,} "
            f"(minimum purchase {unit * min_u} = {unit} × {min_u})."
        )
    units_dec = Decimal(share_units)
    amt = unit * units_dec
    return amt, unit, units_dec
