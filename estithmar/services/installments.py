from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from estithmar import db
from estithmar.models import (
    Contribution,
    InstallmentAllocation,
    InstallmentPlan,
    ShareSubscription,
    get_or_create_settings,
)


def installment_settings() -> dict:
    ex = get_or_create_settings().get_extra()
    return {
        "grace_days": max(0, int(ex.get("installment_grace_days") or 0)),
        "late_fee_percent": _parse_late_fee_percent(ex.get("installment_late_fee_percent")),
        "late_fee_fixed": _parse_late_fee_fixed(ex.get("installment_late_fee_fixed")),
        "allocate_on_verify": bool(ex.get("installment_allocate_on_verify")),
        "reminder_days_ahead": max(0, int(ex.get("installment_reminder_days_ahead") or 3)),
        "require_schedule": ex.get("installment_require_schedule", True) is not False,
        "require_full_schedule": ex.get("installment_require_full_schedule", True) is not False,
        "reminder_cooldown_days": max(1, int(ex.get("installment_reminder_cooldown_days") or 1)),
    }


def _parse_late_fee_percent(raw) -> Decimal:
    try:
        return max(Decimal("0"), Decimal(str(raw or "0")))
    except Exception:
        return Decimal("0")


def _parse_late_fee_fixed(raw) -> Decimal:
    try:
        return max(Decimal("0"), Decimal(str(raw or "0")))
    except Exception:
        return Decimal("0")


def _grace_end(row: InstallmentPlan, cfg: dict) -> date | None:
    if not row.due_date:
        return None
    return row.due_date + timedelta(days=cfg["grace_days"])


def is_row_past_due(row: InstallmentPlan, *, as_of: date | None = None) -> bool:
    if row.status == "Cancelled":
        return False
    today = as_of or date.today()
    cfg = installment_settings()
    grace_end = _grace_end(row, cfg)
    if grace_end is None:
        return False
    paid = row.paid_amount or Decimal("0")
    return grace_end < today and paid < effective_row_due(row, as_of=today, cfg=cfg)


def compute_late_fee(row: InstallmentPlan, *, as_of: date | None = None, cfg: dict | None = None) -> Decimal:
    cfg = cfg or installment_settings()
    if row.status == "Cancelled" or getattr(row, "late_fee_waived", False):
        return Decimal("0")
    today = as_of or date.today()
    grace_end = _grace_end(row, cfg)
    if grace_end is None or grace_end >= today:
        return Decimal("0")
    base = row.due_amount or Decimal("0")
    paid = row.paid_amount or Decimal("0")
    if cfg["late_fee_percent"] > 0:
        nominal = (base * cfg["late_fee_percent"] / Decimal("100")).quantize(Decimal("0.01"))
    elif cfg["late_fee_fixed"] > 0:
        nominal = cfg["late_fee_fixed"]
    else:
        return Decimal("0")
    excess_over_base = max(paid - base, Decimal("0"))
    remaining = (nominal - excess_over_base).quantize(Decimal("0.01"))
    return remaining if remaining > Decimal("0") else Decimal("0")


def row_late_fee_amount(
    row: InstallmentPlan,
    *,
    as_of: date | None = None,
    cfg: dict | None = None,
) -> Decimal:
    """Computed late fee for display/allocation (does not mutate the row)."""
    return compute_late_fee(row, as_of=as_of, cfg=cfg)


def effective_row_due(
    row: InstallmentPlan,
    *,
    as_of: date | None = None,
    cfg: dict | None = None,
    persist: bool = False,
) -> Decimal:
    base = row.due_amount or Decimal("0")
    fee = row_late_fee_amount(row, as_of=as_of, cfg=cfg)
    if persist:
        row.late_fee_amount = fee
    return (base + fee).quantize(Decimal("0.01"))


def active_installment_rows(sub: ShareSubscription) -> list[InstallmentPlan]:
    return [
        x
        for x in sub.installments.order_by(
            InstallmentPlan.due_date.asc(), InstallmentPlan.sequence_no.asc()
        ).all()
        if x.status != "Cancelled"
    ]


def schedule_total_due(sub: ShareSubscription, *, exclude_row_id: int | None = None) -> Decimal:
    total = Decimal("0")
    for row in active_installment_rows(sub):
        if exclude_row_id and row.id == exclude_row_id:
            continue
        total += row.due_amount or Decimal("0")
    return total.quantize(Decimal("0.01"))


def validate_schedule_totals(
    sub: ShareSubscription,
    *,
    extra_due: Decimal = Decimal("0"),
    exclude_row_id: int | None = None,
) -> None:
    total = schedule_total_due(sub, exclude_row_id=exclude_row_id) + (extra_due or Decimal("0"))
    subscribed = (sub.subscribed_amount or Decimal("0")).quantize(Decimal("0.01"))
    if total > subscribed + Decimal("0.01"):
        raise ValueError(
            f"Installment schedule total ({total}) exceeds subscription amount ({subscribed}). "
            "Use Auto-correct due amounts or reduce row amounts."
        )


def validate_sequence_no(
    sub: ShareSubscription,
    sequence_no: int,
    *,
    exclude_row_id: int | None = None,
) -> None:
    seq = int(sequence_no or 1)
    for row in active_installment_rows(sub):
        if exclude_row_id and row.id == exclude_row_id:
            continue
        if row.sequence_no == seq:
            raise ValueError(
                f"Sequence #{seq} is already used on this schedule. Choose a unique sequence number."
            )


def schedule_health_warnings(sub: ShareSubscription, *, as_of: date | None = None) -> list[str]:
    """Human-readable schedule issues for operators correcting mistakes."""
    warnings: list[str] = []
    if (sub.payment_plan or "full") != "installment":
        return warnings
    gap_info = subscription_schedule_gap(sub)
    gap = gap_info["schedule_gap"]
    if abs(gap) > Decimal("0.01"):
        if gap > 0:
            warnings.append(
                f"Schedule is under-subscribed by {gap} — add rows or run Auto-correct due amounts."
            )
        else:
            warnings.append(
                f"Schedule exceeds subscribed amount by {-gap} — reduce row amounts or run Auto-correct."
            )
    active = active_installment_rows(sub)
    seqs = [r.sequence_no for r in active]
    if len(seqs) != len(set(seqs)):
        warnings.append("Duplicate sequence numbers detected — edit rows so each # is unique.")
    sub_paid = gap_info["paid_total"]
    inst_paid = gap_info["installment_paid"]
    pay_gap = (sub_paid - inst_paid).quantize(Decimal("0.01"))
    if abs(pay_gap) > Decimal("0.01"):
        warnings.append(
            f"Payments on subscription ({sub_paid}) do not match installment paid totals ({inst_paid}). "
            "Use Sync payments to schedule or Rebuild from contributions."
        )
    today = as_of or date.today()
    for row in active:
        if row.due_date and row.due_date < today - timedelta(days=365 * 5):
            warnings.append(
                f"Row #{row.sequence_no} has a due date more than 5 years in the past — review or shift dates."
            )
            break
    if active and not schedule_covers_subscription(sub) and sub_paid >= (sub.subscribed_amount or Decimal("0")):
        warnings.append(
            "Subscription is fully paid but the installment schedule does not cover the subscribed amount."
        )
    return warnings


def row_outstanding_balance(row: InstallmentPlan, *, as_of: date | None = None) -> Decimal:
    if row.status == "Cancelled":
        return Decimal("0")
    effective = effective_row_due(row, as_of=as_of)
    paid = row.paid_amount or Decimal("0")
    bal = effective - paid
    return bal if bal > 0 else Decimal("0")


def is_row_overdue_for_display(row: InstallmentPlan, *, as_of: date | None = None) -> bool:
    if row.status == "Cancelled":
        return False
    if row_outstanding_balance(row, as_of=as_of) <= 0:
        return False
    return is_row_past_due(row, as_of=as_of)


def installment_plans_scope_query():
    """Active installment rows on non-cancelled installment subscriptions."""
    return (
        InstallmentPlan.query.join(ShareSubscription, InstallmentPlan.subscription_id == ShareSubscription.id)
        .filter(
            ShareSubscription.payment_plan == "installment",
            ShareSubscription.status != "Cancelled",
            InstallmentPlan.status != "Cancelled",
        )
    )


def installment_late_fee_outstanding(sub: ShareSubscription, *, as_of: date | None = None) -> Decimal:
    if (sub.payment_plan or "full") != "installment":
        return Decimal("0")
    total = Decimal("0")
    for row in active_installment_rows(sub):
        bal = row_outstanding_balance(row, as_of=as_of)
        principal_rem = max((row.due_amount or Decimal("0")) - (row.paid_amount or Decimal("0")), Decimal("0"))
        fee_part = max(bal - principal_rem, Decimal("0"))
        total += fee_part
    return total.quantize(Decimal("0.01"))


def schedule_covers_subscription(sub: ShareSubscription) -> bool:
    gap = subscription_schedule_gap(sub)["schedule_gap"]
    return abs(gap) <= Decimal("0.01")


def summarize_installment_rows(
    rows: list[InstallmentPlan],
    *,
    as_of: date | None = None,
    include_cancelled: bool = False,
) -> dict:
    """Unified overdue count and due balance (includes late fees and grace)."""
    today = as_of or date.today()
    overdue_count = 0
    due_balance = Decimal("0")
    active_count = 0
    for row in rows:
        if row.status == "Cancelled":
            if include_cancelled:
                continue
            continue
        active_count += 1
        bal = row_outstanding_balance(row, as_of=today)
        if bal > 0:
            due_balance += bal
            if is_row_overdue_for_display(row, as_of=today):
                overdue_count += 1
    return {
        "overdue_count": overdue_count,
        "due_balance": due_balance.quantize(Decimal("0.01")),
        "active_count": active_count,
    }


def ensure_installment_schedule_exists(sub: ShareSubscription) -> None:
    cfg = installment_settings()
    if not cfg.get("require_schedule", True):
        return
    if (sub.payment_plan or "full") != "installment":
        return
    if not active_installment_rows(sub):
        raise ValueError(
            "This subscription uses an installment plan but has no schedule defined. "
            "Open Installments and create a schedule before recording payments."
        )


def installment_schedule_satisfied(sub: ShareSubscription) -> bool:
    """True when installment subscriptions meet schedule requirements (or setting is off)."""
    if (sub.payment_plan or "full") != "installment":
        return True
    cfg = installment_settings()
    if not cfg.get("require_schedule", True):
        return True
    return bool(active_installment_rows(sub))


def ensure_installment_schedule_for_certificate(sub: ShareSubscription) -> None:
    if not installment_schedule_satisfied(sub):
        raise ValueError(
            "Cannot confirm or issue a certificate for this installment subscription until "
            "an installment schedule is defined. Open Installments and create the schedule first."
        )
    cfg = installment_settings()
    if cfg.get("require_full_schedule", True) and not schedule_covers_subscription(sub):
        gap = subscription_schedule_gap(sub)["schedule_gap"]
        raise ValueError(
            f"Installment schedule total does not match subscribed amount (gap: {gap}). "
            "Use Auto-correct due amounts or adjust rows before issuing a certificate."
        )


def handle_payment_plan_changed_to_full(subscription_id: int, *, commit: bool = False) -> int:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None or (sub.payment_plan or "full") != "full":
        return 0
    active = active_installment_rows(sub)
    if any((r.paid_amount or Decimal("0")) > 0 for r in active):
        raise ValueError(
            "Cannot switch to full payment while installment rows have payments applied. "
            "Rebuild allocations or cancel paid rows first."
        )
    return cancel_installment_rows_for_subscription(subscription_id, commit=commit)


def sync_orphan_payments_to_installments(subscription_id: int, *, commit: bool = False) -> Decimal:
    """Align installment paid totals with subscription paid_total (both directions)."""
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None or (sub.payment_plan or "full") != "installment":
        return Decimal("0")
    if not active_installment_rows(sub):
        return Decimal("0")
    sub_paid = sub.paid_total()
    inst_paid = sum((r.paid_amount or Decimal("0") for r in active_installment_rows(sub)), Decimal("0"))
    gap = (sub_paid - inst_paid).quantize(Decimal("0.01"))
    if abs(gap) <= Decimal("0.01"):
        return Decimal("0")
    if gap > 0:
        leftover, _ = auto_allocate_payment_to_installments(subscription_id, gap, commit=False)
        adjusted = gap - leftover
    else:
        _, _ = apply_significant_amount_to_installments(subscription_id, gap, commit=False)
        adjusted = gap
    if commit:
        db.session.commit()
    return adjusted


def allocations_for_subscription(subscription_id: int) -> list[dict]:
    rows = (
        InstallmentAllocation.query.join(InstallmentPlan)
        .join(Contribution, InstallmentAllocation.contribution_id == Contribution.id)
        .filter(InstallmentPlan.subscription_id == subscription_id)
        .order_by(InstallmentAllocation.created_at.desc())
        .all()
    )
    out: list[dict] = []
    for a in rows:
        c = a.contribution
        out.append(
            {
                "id": a.id,
                "amount": a.amount,
                "installment_plan_id": a.installment_plan_id,
                "sequence_no": a.installment_plan.sequence_no if a.installment_plan else None,
                "contribution_id": a.contribution_id,
                "receipt_no": c.receipt_no if c else None,
                "contribution_date": c.date if c else None,
                "created_at": a.created_at,
            }
        )
    return out


def migrate_legacy_installment_allocations_if_needed() -> int:
    """One-time backfill of InstallmentAllocation from contributions when rows have paid amounts."""
    settings = get_or_create_settings()
    ex = settings.get_extra()
    if ex.get("installment_allocations_migrated_v1"):
        return 0
    rebuilt = 0
    subs = ShareSubscription.query.filter(
        ShareSubscription.payment_plan == "installment",
        ShareSubscription.status != "Cancelled",
    ).all()
    for sub in subs:
        has_alloc = (
            InstallmentAllocation.query.join(InstallmentPlan)
            .filter(InstallmentPlan.subscription_id == sub.id)
            .limit(1)
            .first()
        )
        inst_paid = sum((r.paid_amount or Decimal("0") for r in active_installment_rows(sub)), Decimal("0"))
        if inst_paid > 0 and has_alloc is None:
            rebuild_allocations_from_contributions(sub.id, commit=False)
            rebuilt += 1
        else:
            sync_orphan_payments_to_installments(sub.id, commit=False)
    ex["installment_allocations_migrated_v1"] = True
    settings.set_extra(ex)
    db.session.commit()
    return rebuilt


def ensure_installment_subscription(sub: ShareSubscription) -> None:
    if (sub.payment_plan or "full") != "installment":
        raise ValueError("Installment schedules apply only to subscriptions with payment plan Installment.")


def recompute_installment_statuses(
    subscription_id: int, *, as_of: date | None = None, commit: bool = False
) -> list[InstallmentPlan]:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")

    today = as_of or date.today()
    cfg = installment_settings()
    rows = (
        sub.installments.order_by(InstallmentPlan.due_date.asc(), InstallmentPlan.sequence_no.asc()).all()
    )
    for row in rows:
        if row.status == "Cancelled":
            continue
        effective_due = effective_row_due(row, as_of=today, cfg=cfg, persist=True)
        paid = row.paid_amount or Decimal("0")
        past_due = is_row_past_due(row, as_of=today)

        if paid >= effective_due and effective_due > 0:
            row.status = "Fully Paid"
        elif paid > 0:
            row.status = "Overdue" if past_due else "Partially Paid"
        elif past_due:
            row.status = "Overdue"
        else:
            row.status = "Pending"

    if commit:
        db.session.commit()
    return rows


def cancel_unpaid_installment_rows(subscription_id: int, *, commit: bool = False) -> int:
    """Remove mistaken unpaid rows (soft-cancel). Rows with payments are kept."""
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        return 0
    n = 0
    for row in active_installment_rows(sub):
        if (row.paid_amount or Decimal("0")) > 0:
            continue
        row.status = "Cancelled"
        n += 1
    if n:
        recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()
    return n


def shift_installment_due_dates(
    subscription_id: int,
    days: int,
    *,
    only_unpaid: bool = True,
    commit: bool = False,
) -> int:
    """Shift due dates by N days (negative allowed). Skips fully paid rows when only_unpaid."""
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        return 0
    delta = timedelta(days=int(days))
    if delta.days == 0:
        return 0
    n = 0
    for row in active_installment_rows(sub):
        if only_unpaid and row.status == "Fully Paid":
            continue
        if row.due_date is None:
            continue
        row.due_date = row.due_date + delta
        n += 1
    if n:
        recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()
    return n


def waive_installment_late_fee(
    row_id: int,
    subscription_id: int,
    *,
    commit: bool = False,
) -> InstallmentPlan:
    row = db.session.get(InstallmentPlan, row_id)
    if row is None or row.subscription_id != subscription_id:
        raise ValueError("Invalid installment row.")
    if row.status == "Cancelled":
        raise ValueError("Cannot waive late fee on a cancelled row.")
    row.late_fee_waived = True
    row.late_fee_amount = Decimal("0")
    recompute_installment_statuses(subscription_id, commit=False)
    if commit:
        db.session.commit()
    return row


def regenerate_future_installment_schedule(
    subscription_id: int,
    *,
    installments_count: int,
    frequency: str = "monthly",
    start_date: date,
    custom_days: int = 30,
    commit: bool = False,
) -> list[InstallmentPlan]:
    """Cancel unpaid rows and regenerate the remaining outstanding balance (keeps paid rows)."""
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    ensure_installment_subscription(sub)

    kept: list[InstallmentPlan] = []
    for row in active_installment_rows(sub):
        paid = row.paid_amount or Decimal("0")
        if paid > 0:
            kept.append(row)
        else:
            row.status = "Cancelled"

    kept_outstanding = sum(
        (row_outstanding_balance(r) for r in kept),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    remaining = (sub.outstanding_balance() - kept_outstanding).quantize(Decimal("0.01"))
    if remaining <= Decimal("0"):
        raise ValueError(
            "No remaining balance to schedule — kept rows already cover the outstanding amount."
        )

    count = max(1, min(60, int(installments_count or 1)))
    freq = frequency if frequency in {"monthly", "weekly", "biweekly", "quarterly", "custom_days"} else "monthly"
    max_seq = max((r.sequence_no or 0 for r in kept), default=0)

    rows: list[InstallmentPlan] = []
    base = (remaining / Decimal(str(count))).quantize(Decimal("0.01"))
    running = Decimal("0")
    for i in range(1, count + 1):
        due_amount = base
        if i == count:
            due_amount = (remaining - running).quantize(Decimal("0.01"))
        running += due_amount
        due_date = _next_due_date(start_date, i, freq, custom_days=custom_days)
        max_seq += 1
        rows.append(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=due_date,
                due_amount=due_amount,
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=max_seq,
            )
        )

    new_total = sum((r.due_amount or Decimal("0") for r in rows), Decimal("0"))
    kept_due = sum((r.due_amount or Decimal("0") for r in kept), Decimal("0"))
    if kept_due + new_total > (sub.subscribed_amount or Decimal("0")) + Decimal("0.01"):
        raise ValueError("Regenerated schedule would exceed the subscription amount.")

    db.session.add_all(rows)
    recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()
    return rows


def recompute_all_active_installment_statuses(*, commit: bool = False) -> int:
    subs = ShareSubscription.query.filter(
        ShareSubscription.payment_plan == "installment",
        ShareSubscription.status != "Cancelled",
    ).all()
    for sub in subs:
        recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()
    return len(subs)


def cancel_installment_rows_for_subscription(subscription_id: int, *, commit: bool = False) -> int:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        return 0
    n = 0
    for row in sub.installments.all():
        if row.status != "Cancelled":
            row.status = "Cancelled"
            n += 1
    if commit:
        db.session.commit()
    return n


def _record_allocation(contribution_id: int, installment_plan_id: int, amount: Decimal) -> None:
    if amount == 0:
        return
    db.session.add(
        InstallmentAllocation(
            contribution_id=contribution_id,
            installment_plan_id=installment_plan_id,
            amount=amount,
        )
    )


def contribution_is_allocated(contribution_id: int) -> bool:
    return (
        InstallmentAllocation.query.filter_by(contribution_id=contribution_id).limit(1).first()
        is not None
    )


def should_allocate_contribution(contribution: Contribution) -> bool:
    if not contribution.subscription_id:
        return False
    sub = db.session.get(ShareSubscription, contribution.subscription_id)
    if sub is None or (sub.payment_plan or "full") != "installment":
        return False
    amount = contribution.amount or Decimal("0")
    if amount <= 0:
        return True
    cfg = installment_settings()
    if cfg["allocate_on_verify"] and not contribution.verified:
        return False
    return True


def apply_significant_amount_to_installments(
    subscription_id: int,
    payment_amount: Decimal,
    *,
    payment_date: date | None = None,
    contribution_id: int | None = None,
    target_installment_id: int | None = None,
    commit: bool = False,
) -> tuple[Decimal, list[InstallmentPlan]]:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    if sub.status == "Cancelled" and (payment_amount or Decimal("0")) > 0:
        raise ValueError("Cannot allocate new payments to a cancelled subscription.")

    today = payment_date or date.today()
    touched: list[InstallmentPlan] = []
    amount_left = Decimal(str(payment_amount or "0"))

    if amount_left == 0:
        return Decimal("0"), []

    rows_asc = (
        sub.installments.order_by(InstallmentPlan.due_date.asc(), InstallmentPlan.sequence_no.asc()).all()
    )

    def _alloc_to_row(row: InstallmentPlan, alloc: Decimal) -> None:
        nonlocal amount_left
        if alloc <= 0:
            return
        paid = row.paid_amount or Decimal("0")
        row.paid_amount = paid + alloc
        amount_left -= alloc
        touched.append(row)
        if contribution_id:
            _record_allocation(contribution_id, row.id, alloc)

    if amount_left > 0:
        ordered: list[InstallmentPlan] = []
        if target_installment_id:
            target = next((r for r in rows_asc if r.id == target_installment_id), None)
            if target is None or target.subscription_id != sub.id:
                raise ValueError("Invalid target installment row.")
            if target.status != "Cancelled":
                ordered.append(target)
        for row in rows_asc:
            if row.status == "Cancelled":
                continue
            if target_installment_id and row.id == target_installment_id:
                continue
            ordered.append(row)

        for row in ordered:
            if amount_left <= 0:
                break
            if row.status == "Cancelled":
                continue
            effective_due = effective_row_due(row, as_of=today)
            paid = row.paid_amount or Decimal("0")
            bal = effective_due - paid
            if bal <= 0:
                row.status = "Fully Paid"
                continue
            alloc = bal if amount_left >= bal else amount_left
            _alloc_to_row(row, alloc)
    else:
        remaining = -amount_left
        if contribution_id:
            allocs = (
                InstallmentAllocation.query.filter_by(contribution_id=contribution_id)
                .order_by(InstallmentAllocation.id.desc())
                .all()
            )
            for alloc in allocs:
                if remaining <= 0:
                    break
                row = alloc.installment_plan
                take = alloc.amount if remaining >= alloc.amount else remaining
                row.paid_amount = (row.paid_amount or Decimal("0")) - take
                remaining -= take
                touched.append(row)
                if take >= alloc.amount:
                    db.session.delete(alloc)
                else:
                    alloc.amount = (alloc.amount or Decimal("0")) - take
            amount_left = -remaining
        else:
            for row in reversed(rows_asc):
                if remaining <= 0:
                    break
                if row.status == "Cancelled":
                    continue
                paid = row.paid_amount or Decimal("0")
                if paid <= 0:
                    continue
                take = paid if remaining >= paid else remaining
                row.paid_amount = paid - take
                remaining -= take
                touched.append(row)
            amount_left = -remaining

    recompute_installment_statuses(sub.id, as_of=today, commit=False)

    if commit:
        db.session.commit()
    return amount_left, touched


def auto_allocate_payment_to_installments(
    subscription_id: int,
    payment_amount: Decimal,
    *,
    payment_date: date | None = None,
    contribution_id: int | None = None,
    target_installment_id: int | None = None,
    commit: bool = False,
) -> tuple[Decimal, list[InstallmentPlan]]:
    if (payment_amount or Decimal("0")) < 0:
        raise ValueError("Use apply_significant_amount_to_installments for negative (reversal) amounts.")
    return apply_significant_amount_to_installments(
        subscription_id,
        payment_amount,
        payment_date=payment_date,
        contribution_id=contribution_id,
        target_installment_id=target_installment_id,
        commit=commit,
    )


def allocate_contribution_to_installments(
    contribution: Contribution,
    *,
    target_installment_id: int | None = None,
    force: bool = False,
    commit: bool = False,
) -> tuple[Decimal, list[InstallmentPlan]]:
    if not contribution.subscription_id:
        return Decimal("0"), []
    if not force and not should_allocate_contribution(contribution):
        return Decimal("0"), []
    if contribution.id and contribution_is_allocated(contribution.id):
        return Decimal("0"), []
    leftover, touched = auto_allocate_payment_to_installments(
        contribution.subscription_id,
        contribution.amount or Decimal("0"),
        payment_date=contribution.date,
        contribution_id=contribution.id,
        target_installment_id=target_installment_id,
        commit=False,
    )
    sync_orphan_payments_to_installments(contribution.subscription_id, commit=False)
    if commit:
        db.session.commit()
    return leftover, touched


def unallocate_contribution_from_installments(
    contribution: Contribution,
    *,
    commit: bool = False,
) -> tuple[Decimal, list[InstallmentPlan]]:
    if not contribution.subscription_id or not contribution.id:
        return Decimal("0"), []
    amount = contribution.amount or Decimal("0")
    if amount > 0 and not contribution_is_allocated(contribution.id):
        return Decimal("0"), []
    if contribution_is_allocated(contribution.id):
        return apply_significant_amount_to_installments(
            contribution.subscription_id,
            -amount,
            payment_date=contribution.date,
            contribution_id=contribution.id,
            commit=commit,
        )
    if amount < 0:
        return apply_significant_amount_to_installments(
            contribution.subscription_id,
            -amount,
            payment_date=contribution.date,
            contribution_id=contribution.id,
            commit=commit,
        )
    return Decimal("0"), []


def rebalance_installment_due_amounts(subscription_id: int, *, commit: bool = False) -> int:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    ensure_installment_subscription(sub)
    active_rows = active_installment_rows(sub)
    if not active_rows:
        return 0

    target_total = (sub.subscribed_amount or Decimal("0")).quantize(Decimal("0.01"))
    locked_rows: list[InstallmentPlan] = []
    adjustable_rows: list[InstallmentPlan] = []
    for row in active_rows:
        paid = (row.paid_amount or Decimal("0")).quantize(Decimal("0.01"))
        if row.status == "Fully Paid":
            row.due_amount = max((row.due_amount or Decimal("0")).quantize(Decimal("0.01")), paid)
            locked_rows.append(row)
        else:
            row.due_amount = paid
            adjustable_rows.append(row)

    locked_total = sum(((r.due_amount or Decimal("0")) for r in locked_rows), Decimal("0")).quantize(
        Decimal("0.01")
    )
    adjustable_base = sum(((r.due_amount or Decimal("0")) for r in adjustable_rows), Decimal("0")).quantize(
        Decimal("0.01")
    )
    alloc_total = (target_total - locked_total - adjustable_base).quantize(Decimal("0.01"))
    if alloc_total < Decimal("0"):
        raise ValueError(
            "Cannot auto-correct: paid/locked installment rows already exceed the subscription amount."
        )

    if adjustable_rows:
        base = (alloc_total / Decimal(str(len(adjustable_rows)))).quantize(Decimal("0.01"))
        running = Decimal("0")
        for idx, row in enumerate(adjustable_rows, start=1):
            add_amt = base
            if idx == len(adjustable_rows):
                add_amt = (alloc_total - running).quantize(Decimal("0.01"))
            row.due_amount = ((row.due_amount or Decimal("0")) + add_amt).quantize(Decimal("0.01"))
            running += add_amt

    recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()
    return len(active_rows)


def _next_due_date(start: date, index: int, frequency: str, *, custom_days: int = 30) -> date:
    if frequency == "weekly":
        return start + timedelta(days=(index - 1) * 7)
    if frequency == "biweekly":
        return start + timedelta(days=(index - 1) * 14)
    if frequency == "quarterly":
        return start + relativedelta(months=(index - 1) * 3)
    if frequency == "custom_days":
        step = max(1, int(custom_days or 30))
        return start + timedelta(days=(index - 1) * step)
    return start + relativedelta(months=index - 1)


def generate_installment_schedule(
    subscription_id: int,
    *,
    installments_count: int,
    frequency: str = "monthly",
    start_date: date,
    down_payment: Decimal = Decimal("0"),
    replace_existing: bool = False,
    custom_days: int = 30,
    commit: bool = False,
) -> list[InstallmentPlan]:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    ensure_installment_subscription(sub)

    active_rows = active_installment_rows(sub)
    if active_rows and not replace_existing:
        raise ValueError("Active installment rows exist. Enable replace to regenerate the schedule.")

    if replace_existing and active_rows:
        for row in active_rows:
            if (row.paid_amount or Decimal("0")) > 0:
                raise ValueError("Cannot replace schedule while rows have payments applied.")
            row.status = "Cancelled"

    total = sub.outstanding_balance()
    if total <= 0:
        raise ValueError("No outstanding balance left to split into installments.")

    down = (down_payment or Decimal("0")).quantize(Decimal("0.01"))
    if down < 0 or down >= total:
        raise ValueError("Down payment must be between zero and the outstanding balance.")

    remaining = (total - down).quantize(Decimal("0.01"))
    count = max(1, min(60, int(installments_count or 1)))
    freq = frequency if frequency in {"monthly", "weekly", "biweekly", "quarterly", "custom_days"} else "monthly"

    rows: list[InstallmentPlan] = []
    seq = 1
    if down > 0:
        rows.append(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=start_date,
                due_amount=down,
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=seq,
            )
        )
        seq += 1

    if remaining > 0:
        base = (remaining / Decimal(str(count))).quantize(Decimal("0.01"))
        running = Decimal("0")
        offset = 1 if down > 0 else 0
        for i in range(1, count + 1):
            due_amount = base
            if i == count:
                due_amount = (remaining - running).quantize(Decimal("0.01"))
            running += due_amount
            due_date = _next_due_date(start_date, i + offset, freq, custom_days=custom_days)
            rows.append(
                InstallmentPlan(
                    subscription_id=sub.id,
                    due_date=due_date,
                    due_amount=due_amount,
                    paid_amount=Decimal("0"),
                    status="Pending",
                    sequence_no=seq,
                )
            )
            seq += 1

    new_total = sum((r.due_amount or Decimal("0") for r in rows), Decimal("0"))
    if new_total > (sub.subscribed_amount or Decimal("0")) + Decimal("0.01"):
        raise ValueError("Generated schedule exceeds the subscription amount.")
    db.session.add_all(rows)
    recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()
    return rows


def rebuild_allocations_from_contributions(subscription_id: int, *, commit: bool = False) -> None:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")

    InstallmentAllocation.query.filter(
        InstallmentAllocation.contribution_id.in_(
            db.session.query(Contribution.id).filter(Contribution.subscription_id == subscription_id)
        )
    ).delete(synchronize_session=False)

    for row in sub.installments.all():
        row.paid_amount = Decimal("0")
        row.late_fee_amount = Decimal("0")
        row.late_fee_waived = False
        if row.status != "Cancelled":
            row.status = "Pending"

    contribs = sub.contributions.order_by(Contribution.date.asc(), Contribution.id.asc()).all()
    for c in contribs:
        amt = c.amount or Decimal("0")
        if amt == 0:
            continue
        if amt > 0:
            allocate_contribution_to_installments(c, force=True, commit=False)
        else:
            apply_significant_amount_to_installments(
                sub.id,
                amt,
                payment_date=c.date,
                contribution_id=c.id,
                commit=False,
            )

    sync_orphan_payments_to_installments(sub.id, commit=False)
    recompute_installment_statuses(sub.id, commit=False)
    if commit:
        db.session.commit()


def subscription_schedule_gap(sub: ShareSubscription) -> dict:
    scheduled = schedule_total_due(sub)
    subscribed = sub.subscribed_amount or Decimal("0")
    paid = sub.paid_total()
    return {
        "subscribed": subscribed,
        "scheduled_due": scheduled,
        "schedule_gap": (subscribed - scheduled).quantize(Decimal("0.01")),
        "paid_total": paid,
        "outstanding": sub.outstanding_balance(),
        "installment_paid": sum(
            (r.paid_amount or Decimal("0") for r in active_installment_rows(sub)), Decimal("0")
        ),
    }


def subscription_schedule_adherence(sub: ShareSubscription, *, as_of: date | None = None) -> dict:
    """Adherence = rows fully paid or not yet overdue / total active rows."""
    today = as_of or date.today()
    good = 0
    overdue = 0
    partial = 0
    pending = 0
    fully_paid = 0
    rows = active_installment_rows(sub)
    for row in rows:
        paid = row.paid_amount or Decimal("0")
        effective = effective_row_due(row, as_of=today)
        bal = row_outstanding_balance(row, as_of=today)
        if bal <= 0 and paid > 0:
            fully_paid += 1
            good += 1
        elif is_row_overdue_for_display(row, as_of=today):
            overdue += 1
        elif paid > 0:
            partial += 1
            good += 1
        else:
            pending += 1
            good += 1
    total = len(rows)
    adherence_pct = (
        (Decimal(str(good)) / Decimal(str(total)) * Decimal("100") if total else Decimal("0"))
    ).quantize(Decimal("0.01"))
    return {
        "on_time": good,
        "overdue": overdue,
        "pending_future": pending,
        "partial": partial,
        "fully_paid": fully_paid,
        "total_rows": total,
        "adherence_pct": adherence_pct,
    }


def collect_installment_report_rows(
    rows: list[InstallmentPlan],
    *,
    as_of: date | None = None,
) -> tuple[list[tuple[InstallmentPlan, Decimal]], list[tuple[InstallmentPlan, Decimal]], list[dict]]:
    today = as_of or date.today()
    overdue_rows: list[tuple[InstallmentPlan, Decimal]] = []
    unpaid_rows: list[tuple[InstallmentPlan, Decimal]] = []
    gap_rows: list[dict] = []
    seen_subs: set[int] = set()

    for r in rows:
        if r.status == "Cancelled":
            continue
        effective = effective_row_due(r, as_of=today)
        bal = effective - (r.paid_amount or Decimal("0"))
        if bal > 0:
            unpaid_rows.append((r, bal))
            if is_row_overdue_for_display(r, as_of=today):
                overdue_rows.append((r, bal))
        sub = r.subscription
        if sub and sub.id not in seen_subs and (sub.payment_plan or "full") == "installment":
            seen_subs.add(sub.id)
            gap = subscription_schedule_gap(sub)
            gap["subscription"] = sub
            gap_rows.append(gap)

    return overdue_rows, unpaid_rows, gap_rows


def installment_schedule_for_receipt(
    sub: ShareSubscription,
    *,
    contribution: Contribution | None = None,
) -> list[dict]:
    today = date.today()
    out: list[dict] = []
    for row in active_installment_rows(sub):
        effective = effective_row_due(row, as_of=today)
        bal = effective - (row.paid_amount or Decimal("0"))
        if bal < 0:
            bal = Decimal("0")
        alloc_amt = Decimal("0")
        if contribution and contribution.id:
            alloc_amt = sum(
                (
                    a.amount or Decimal("0")
                    for a in row.allocations.filter_by(contribution_id=contribution.id).all()
                ),
                Decimal("0"),
            )
        out.append(
            {
                "row": row,
                "effective_due": effective,
                "balance": bal,
                "allocated_this_payment": alloc_amt,
                "is_overdue": is_row_overdue_for_display(row, as_of=today),
            }
        )
    return out
