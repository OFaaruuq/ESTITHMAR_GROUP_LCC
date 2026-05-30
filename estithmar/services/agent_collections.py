"""Agent-scoped collection helpers — overdue members to call and follow up."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from estithmar.models import Member, ShareSubscription
from estithmar.services.installments import (
    collect_installment_report_rows,
    installment_plans_scope_query,
    recompute_all_active_installment_statuses,
)


def collect_agent_overdue_members(
    agent_id: int | None = None,
    *,
    as_of: date | None = None,
    recompute: bool = True,
) -> list[dict]:
    """Members with overdue installment rows, grouped for agent collection follow-up."""
    if recompute:
        recompute_all_active_installment_statuses(commit=True)

    today = as_of or date.today()
    query = installment_plans_scope_query().join(Member, ShareSubscription.member_id == Member.id)
    if agent_id is not None:
        query = query.filter(Member.agent_id == agent_id)

    rows = query.all()
    overdue_rows, _, _ = collect_installment_report_rows(rows, as_of=today)

    by_member: dict[int, dict] = {}
    for row, bal in overdue_rows:
        sub = row.subscription
        member = sub.member if sub else None
        if not member:
            continue
        mid = member.id
        if mid not in by_member:
            by_member[mid] = {
                "member": member,
                "overdue_balance": Decimal("0"),
                "overdue_row_count": 0,
                "max_days_late": 0,
                "subscriptions": {},
                "rows": [],
            }
        entry = by_member[mid]
        entry["overdue_balance"] += bal
        entry["overdue_row_count"] += 1
        if row.due_date:
            days_late = max(0, (today - row.due_date).days)
            entry["max_days_late"] = max(entry["max_days_late"], days_late)
        if sub:
            entry["subscriptions"][sub.id] = sub
        entry["rows"].append({"row": row, "balance": bal, "subscription": sub})

    result: list[dict] = []
    for entry in by_member.values():
        result.append(
            {
                "member": entry["member"],
                "overdue_balance": entry["overdue_balance"].quantize(Decimal("0.01")),
                "overdue_row_count": entry["overdue_row_count"],
                "max_days_late": entry["max_days_late"],
                "subscriptions": list(entry["subscriptions"].values()),
                "rows": entry["rows"],
            }
        )

    result.sort(key=lambda x: (-x["max_days_late"], -float(x["overdue_balance"])))
    return result


def summarize_agent_overdue(agent_id: int | None = None, *, as_of: date | None = None) -> dict:
    """Totals for dashboard / email header."""
    members = collect_agent_overdue_members(agent_id, as_of=as_of, recompute=False)
    total_balance = sum((m["overdue_balance"] for m in members), Decimal("0"))
    total_rows = sum((m["overdue_row_count"] for m in members), 0)
    return {
        "member_count": len(members),
        "overdue_row_count": total_rows,
        "overdue_balance": total_balance.quantize(Decimal("0.01")),
    }
