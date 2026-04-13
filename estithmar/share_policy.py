"""Fixed share purchase rules for new subscriptions (whole shares only)."""

from __future__ import annotations

from decimal import Decimal

# Business rules: one share = unit price; members buy a whole number of shares in [min, max].
SHARE_UNIT_PRICE = Decimal("30")
MIN_SHARE_UNITS = 36
MAX_SHARE_UNITS = 100_000


def min_subscribed_amount() -> Decimal:
    return SHARE_UNIT_PRICE * MIN_SHARE_UNITS


def max_subscribed_amount() -> Decimal:
    return SHARE_UNIT_PRICE * MAX_SHARE_UNITS


def resolve_share_subscription_amounts(*, share_units: int | None) -> tuple[Decimal, Decimal, Decimal]:
    """Return (subscribed_amount, share_unit_price, share_units_subscribed) for a valid purchase."""
    if share_units is None:
        raise ValueError("Number of shares is required.")
    if share_units < MIN_SHARE_UNITS or share_units > MAX_SHARE_UNITS:
        raise ValueError(
            f"Number of shares must be between {MIN_SHARE_UNITS:,} and {MAX_SHARE_UNITS:,} "
            f"(minimum purchase {min_subscribed_amount()} = {SHARE_UNIT_PRICE} × {MIN_SHARE_UNITS})."
        )
    unit = SHARE_UNIT_PRICE
    units_dec = Decimal(share_units)
    amt = unit * units_dec
    return amt, unit, units_dec
