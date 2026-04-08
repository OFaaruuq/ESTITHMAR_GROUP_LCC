"""
Profit distribution engine (critical business logic).

Ownership % = member paid (real money) / total paid (all participating members).
Member profit share = ownership % × profit amount to distribute.

Basis is always actual payments (contributions), never promised/subscribed amounts,
except where legacy policy "fully_paid_only" gates participation (must be Fully Paid)
while still using paid_total() as the numeric basis.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from istithmar.models import Member, get_or_create_settings

# Currency precision for eligible paid basis (numerator/denominator must use the same rule).
_MONEY = Decimal("0.01")


def _money_quantize(d: Decimal) -> Decimal:
    return d.quantize(_MONEY, rounding=ROUND_HALF_UP)

if TYPE_CHECKING:
    from istithmar.models import Investment


def profit_basis_verified_only() -> bool:
    """When True, only verified contributions count toward paid basis (stricter eligibility)."""
    return get_or_create_settings().get_extra().get("profit_basis_verified_only") is True


def member_eligible_paid_for_profit(member: Member, inv: Investment) -> Decimal:
    """Paid amount used as the profit-sharing numerator (respects investment scope + verified-only setting)."""
    s = get_or_create_settings()
    v = profit_basis_verified_only()
    if s.get_flag("profit_use_investment_scope", default=False):
        return member.eligible_profit_basis_for_investment(inv.id, verified_only=v)
    return member.eligible_profit_basis(verified_only=v)


def eligible_member_pairs_for_investment(
    inv: Investment,
) -> tuple[list[tuple[Member, Decimal]], Decimal]:
    """
    Active members with positive eligible paid basis for this investment context, and their sum.
    This sum is the denominator in §11.1 (total confirmed/eligible paid contributions for the pool).
    """
    active_members = Member.query.filter_by(status="Active").all()
    eligible_pairs: list[tuple[Member, Decimal]] = []
    total_eligible = Decimal("0")
    for m in active_members:
        el = member_eligible_paid_for_profit(m, inv)
        el_q = _money_quantize(el)
        if el_q > 0:
            eligible_pairs.append((m, el_q))
            total_eligible += el_q
    return eligible_pairs, total_eligible


def eligible_pools_for_investments(investments: list[Investment]) -> dict[int, Decimal]:
    """
    Eligible paid basis per investment (denominator for ownership %), in one member scan.
    Used on the profit distribution screen to show pool size next to each open vehicle.
    """
    if not investments:
        return {}
    active_members = Member.query.filter_by(status="Active").all()
    pools: dict[int, Decimal] = {inv.id: Decimal("0") for inv in investments}
    for m in active_members:
        for inv in investments:
            el = member_eligible_paid_for_profit(m, inv)
            el_q = _money_quantize(el)
            if el_q > 0:
                pools[inv.id] += el_q
    return {k: _money_quantize(v) for k, v in pools.items()}


def allocate_profit_shares(
    eligible_pairs: list[tuple[Any, Decimal]],
    profit_amount: Decimal,
    total_eligible: Decimal,
) -> list[dict[str, Any]]:
    """
    Core §11.1 math: ownership % = eligible / total_eligible; member profit = ownership % × profit_amount.
    ``eligible_pairs`` must use the same quantized basis as ``total_eligible`` (sum of eligibles).
    Remainder cents go to the last member so the row amounts sum exactly to ``profit_amount``.
    """
    preview_rows: list[dict[str, Any]] = []
    for m, eligible_amt in eligible_pairs:
        pct = (eligible_amt / total_eligible) * Decimal("100")
        share = (eligible_amt / total_eligible) * profit_amount
        preview_rows.append(
            {
                "member": m,
                "eligible_amount": eligible_amt,
                "pct": pct.quantize(Decimal("0.0001")),
                "share": _money_quantize(share),
            }
        )

    total_shares = sum((r["share"] for r in preview_rows), Decimal("0"))
    diff = _money_quantize(profit_amount - total_shares)
    if diff != 0 and preview_rows:
        last = preview_rows[-1]
        last["share"] = _money_quantize(last["share"] + diff)

    return preview_rows


def build_profit_distribution_preview(
    inv: Investment,
    profit_amount: Decimal,
) -> tuple[list[dict[str, Any]], Decimal]:
    """
    Build member rows for preview/confirm. Each row: member, eligible_amount (paid basis),
    pct (ownership %), share (profit slice).

    Reconciles cent-level rounding so sum(shares) == profit_amount when rows exist.
    """
    if profit_amount <= 0:
        return [], Decimal("0")

    eligible_pairs, total_eligible = eligible_member_pairs_for_investment(inv)
    if total_eligible <= 0 or not eligible_pairs:
        return [], Decimal("0")

    preview_rows = allocate_profit_shares(eligible_pairs, profit_amount, total_eligible)
    return preview_rows, total_eligible


def policy_label_for_batch() -> str:
    """Stored on ProfitDistributionBatch.policy_used for audit."""
    s = get_or_create_settings()
    if s.get_flag("profit_use_investment_scope", default=False):
        return "paid_real_money_investment_scoped"
    return "paid_real_money_global_pool"
