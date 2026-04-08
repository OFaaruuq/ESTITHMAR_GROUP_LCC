from __future__ import annotations

from decimal import Decimal

from istithmar.models import Contribution, ShareSubscription


def subscription_payment_running_rows(sub: ShareSubscription) -> list[dict]:
    """All linked contributions in order, with cumulative paid, balance, and % paid after each row."""
    rows = (
        sub.contributions.order_by(Contribution.date.asc(), Contribution.id.asc()).all()
    )
    target = sub.subscribed_amount or Decimal("0")
    cum = Decimal("0")
    out: list[dict] = []
    for row in rows:
        cum += row.amount or Decimal("0")
        bal = target - cum
        if bal < 0:
            bal = Decimal("0")
        pct = (cum / target * Decimal("100")) if target > 0 else Decimal("0")
        if pct > 100:
            pct = Decimal("100")
        out.append(
            {
                "contribution": row,
                "cum_paid": cum,
                "balance_after": bal,
                "pct_paid": pct.quantize(Decimal("0.01")),
            }
        )
    return out


def max_payment_for_subscription(sub: ShareSubscription) -> Decimal:
    """Remaining balance that can still be applied (no overpayment)."""
    return sub.outstanding_balance()
