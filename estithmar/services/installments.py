from __future__ import annotations

from datetime import date
from decimal import Decimal

from estithmar import db
from estithmar.models import InstallmentPlan, ShareSubscription


def recompute_installment_statuses(
    subscription_id: int, *, as_of: date | None = None, commit: bool = False
) -> list[InstallmentPlan]:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")

    today = as_of or date.today()
    rows = (
        sub.installments.order_by(InstallmentPlan.due_date.asc(), InstallmentPlan.sequence_no.asc()).all()
    )
    for row in rows:
        if row.status == "Cancelled":
            continue
        due = row.due_amount or Decimal("0")
        paid = row.paid_amount or Decimal("0")
        if paid <= 0:
            row.status = "Overdue" if row.due_date < today else "Pending"
        elif paid >= due and due > 0:
            row.status = "Fully Paid"
        else:
            row.status = "Partially Paid"

    if commit:
        db.session.commit()
    return rows


def auto_allocate_payment_to_installments(
    subscription_id: int,
    payment_amount: Decimal,
    *,
    payment_date: date | None = None,
    commit: bool = False,
) -> tuple[Decimal, list[InstallmentPlan]]:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    if sub.status == "Cancelled":
        raise ValueError("Cannot allocate against a cancelled subscription.")

    amount_left = Decimal(str(payment_amount or "0"))
    if amount_left <= 0:
        return Decimal("0"), []

    today = payment_date or date.today()
    touched: list[InstallmentPlan] = []
    rows = (
        sub.installments.order_by(InstallmentPlan.due_date.asc(), InstallmentPlan.sequence_no.asc()).all()
    )
    for row in rows:
        if amount_left <= 0:
            break
        if row.status == "Cancelled":
            continue
        due = row.due_amount or Decimal("0")
        paid = row.paid_amount or Decimal("0")
        bal = due - paid
        if bal <= 0:
            row.status = "Fully Paid"
            continue
        alloc = bal if amount_left >= bal else amount_left
        row.paid_amount = paid + alloc
        amount_left -= alloc
        touched.append(row)

    recompute_installment_statuses(sub.id, as_of=today, commit=False)

    if commit:
        db.session.commit()
    return amount_left, touched
