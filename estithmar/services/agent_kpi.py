"""Aggregated portfolio metrics for an agent (members, subscriptions, payments, balance)."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from estithmar import db
from estithmar.models import (
    Agent,
    Contribution,
    InstallmentPlan,
    Member,
    ShareCertificate,
    ShareSubscription,
    get_or_create_settings,
)

logger = logging.getLogger(__name__)


def compute_agent_kpis(agent_id: int) -> dict:
    """
    Return a dict of KPIs for all members (and their subscriptions) assigned to the agent.
    All money fields are Decimal; counts are int.
    """
    a = db.session.get(Agent, agent_id)
    if not a:
        return {}
    try:
        return _compute_agent_kpis_for_agent(a, agent_id)
    except Exception:
        logger.exception("compute_agent_kpis failed (agent_id=%s)", agent_id)
        return {}


def _compute_agent_kpis_for_agent(a: Agent, agent_id: int) -> dict:
    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"

    mids = [m[0] for m in db.session.query(Member.id).filter(Member.agent_id == agent_id).all()]
    members_total = len(mids)
    members_active = (
        db.session.query(func.count(Member.id))
        .filter(Member.agent_id == agent_id, Member.status == "Active")
        .scalar()
        or 0
    )

    if mids:
        net_col = (
            db.session.query(func.coalesce(func.sum(Contribution.amount), 0))
            .select_from(Contribution)
            .filter(Contribution.member_id.in_(mids))
            .scalar()
        )
    else:
        net_col = 0
    total_collected = _dec(net_col)

    receipts_count = 0
    if mids:
        receipts_count = (
            Contribution.query.filter(
                Contribution.member_id.in_(mids),
                Contribution.reversal_of_id.is_(None),
            )
            .count()
        )

    subs: list[ShareSubscription] = []
    if mids:
        subs = (
            ShareSubscription.query.options(joinedload(ShareSubscription.certificate))
            .join(Member, ShareSubscription.member_id == Member.id)
            .filter(Member.agent_id == agent_id)
            .all()
        )

    status_counter = Counter(s.status for s in subs)
    total_subscribed = Decimal("0")
    total_outstanding = Decimal("0")
    fully_paid_subscribed_value = Decimal("0")
    confirmed_count = 0
    for s in subs:
        if s.status == "Cancelled":
            continue
        total_subscribed += s.subscribed_amount or Decimal("0")
        total_outstanding += s.outstanding_balance()
        if s.status == "Fully Paid":
            fully_paid_subscribed_value += s.subscribed_amount or Decimal("0")
        if s.is_share_confirmed:
            confirmed_count += 1

    installment_overdue = 0
    installment_due_balance = Decimal("0")
    today = date.today()
    inst_q = (
        db.session.query(InstallmentPlan)
        .join(ShareSubscription, InstallmentPlan.subscription_id == ShareSubscription.id)
        .join(Member, ShareSubscription.member_id == Member.id)
        .filter(Member.agent_id == agent_id)
    )
    for row in inst_q:
        if row.status == "Cancelled":
            continue
        bal = (row.due_amount or Decimal("0")) - (row.paid_amount or Decimal("0"))
        if bal > 0:
            installment_due_balance += bal
            is_overdue = row.status == "Overdue" or (
                row.due_date is not None
                and row.due_date < today
                and row.status in {"Pending", "Partially Paid"}
            )
            if is_overdue:
                installment_overdue += 1

    certificates_issued = 0
    pending_certs = 0
    if mids:
        certificates_issued = (
            ShareCertificate.query.join(Member, ShareCertificate.member_id == Member.id)
            .filter(Member.agent_id == agent_id, ShareCertificate.status == "Issued")
            .count()
        )
        for s in subs:
            if s.status != "Fully Paid" or s.status == "Cancelled":
                continue
            if s.certificate is None or s.certificate.status != "Issued":
                pending_certs += 1

    return {
        "agent": a,
        "agent_id_display": a.agent_id,
        "agent_name": a.full_name,
        "members_total": int(members_total),
        "members_active": int(members_active),
        "receipts_count": int(receipts_count),
        "total_collected": total_collected,
        "total_subscribed": total_subscribed,
        "total_outstanding": total_outstanding,
        "fully_paid_value": fully_paid_subscribed_value,
        "confirmed_subscriptions": int(confirmed_count),
        "status_counter": status_counter,
        "installment_overdue_count": int(installment_overdue),
        "installment_due_balance": installment_due_balance,
        "certificates_issued": int(certificates_issued),
        "pending_certificates": int(pending_certs),
        "subscriptions_count": len(subs),
        "currency_symbol": sym,
        "currency_code": cur,
    }


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))
