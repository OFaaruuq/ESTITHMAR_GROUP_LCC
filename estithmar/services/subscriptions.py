from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from estithmar import db
from estithmar.models import AuditLog, Member, ShareSubscription, next_subscription_no
from estithmar.share_policy import resolve_share_subscription_amounts


def create_subscription(
    *,
    member_id: int,
    share_units: int,
    payment_plan: str = "full",
    eligibility_policy: str = "paid_proportional",
    subscription_date=None,
    agent_id: int | None = None,
    investment_id: int | None = None,
    commit: bool = True,
) -> ShareSubscription:
    member = db.session.get(Member, member_id)
    if member is None:
        raise ValueError("Invalid member.")
    subscribed_amount, share_unit_price, share_units_subscribed = resolve_share_subscription_amounts(
        share_units=share_units
    )
    if payment_plan not in {"full", "installment"}:
        raise ValueError("Invalid payment plan.")
    if eligibility_policy not in {"paid_proportional", "fully_paid_only"}:
        raise ValueError("Invalid eligibility policy.")
    if investment_id is not None:
        from estithmar.models import Investment

        if db.session.get(Investment, investment_id) is None:
            raise ValueError("Invalid investment.")

    sub_date = subscription_date if subscription_date is not None else date.today()

    sub = ShareSubscription(
        subscription_no=next_subscription_no(),
        member_id=member.id,
        agent_id=agent_id if agent_id is not None else member.agent_id,
        subscribed_amount=subscribed_amount,
        share_unit_price=share_unit_price,
        share_units_subscribed=share_units_subscribed,
        payment_plan=payment_plan,
        subscription_date=sub_date,
        status="Pending",
        eligibility_policy=eligibility_policy,
        investment_id=investment_id,
    )
    db.session.add(sub)
    db.session.flush()
    # Ensures status matches rules (Pending: paid_total==0) and sets timestamps consistently.
    recompute_subscription_status(sub.id, commit=False)
    if commit:
        db.session.commit()
    return sub


def compute_subscription_paid_total(subscription_id: int) -> Decimal:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    return sub.paid_total()


def compute_subscription_balance(subscription_id: int) -> Decimal:
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    return sub.outstanding_balance()


def recompute_subscription_status(subscription_id: int, *, commit: bool = False) -> ShareSubscription:
    """Update status from linked payments.

    Share confirmation (business rule): when paid_total equals subscribed_amount (no overpayment
    allowed at entry, so typically paid == target), set status Fully Paid, set confirmed_at
    (CONFIRMED), and callers may trigger certificate eligibility (e.g. maybe_auto_issue_certificate).
    """
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    if sub.status == "Cancelled":
        return sub

    paid = sub.paid_total()
    target = sub.subscribed_amount or Decimal("0")

    if paid <= 0:
        sub.status = "Pending"
        sub.confirmed_at = None
    elif target > 0 and paid >= target:
        # Fully paid: paid matches or reaches subscribed total (overpayment blocked when recording payments).
        sub.status = "Fully Paid"
        if sub.confirmed_at is None:
            sub.confirmed_at = datetime.utcnow()
            db.session.add(
                AuditLog(
                    action="subscription_share_confirmed",
                    entity_type="ShareSubscription",
                    entity_id=sub.id,
                    details=f"subscription_no={sub.subscription_no} paid_total={paid} subscribed_amount={target}",
                )
            )
    else:
        sub.status = "Partially Paid"
        sub.confirmed_at = None

    if commit:
        db.session.commit()
    return sub


def confirm_subscription_if_fully_paid(subscription_id: int, *, commit: bool = False) -> bool:
    sub = recompute_subscription_status(subscription_id, commit=False)
    confirmed = sub.status == "Fully Paid"
    if commit:
        db.session.commit()
    return confirmed
