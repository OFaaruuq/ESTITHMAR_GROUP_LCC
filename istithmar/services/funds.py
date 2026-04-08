"""Pooled funds: member contributions vs investment allocations (business doc §7–8)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from istithmar import db
from istithmar.models import Contribution, Investment, Project


def total_member_contributions_collected(verified_only: bool = False) -> Decimal:
    """All recorded member payments (central pool source). When verified_only is True, only verified contributions count."""
    q = db.session.query(func.coalesce(func.sum(Contribution.amount), 0))
    if verified_only:
        q = q.filter(Contribution.verified.is_(True))
    v = q.scalar() or 0
    return Decimal(str(v))


def total_invested_across_investments(exclude_investment_id: int | None = None) -> Decimal:
    """Sum of amounts allocated to investment vehicles (optionally exclude one row for edit)."""
    q = db.session.query(func.coalesce(func.sum(Investment.total_amount_invested), 0))
    if exclude_investment_id is not None:
        q = q.filter(Investment.id != exclude_investment_id)
    v = q.scalar() or 0
    return Decimal(str(v))


def available_pool_for_investment(
    exclude_investment_id: int | None = None, verified_only: bool = False
) -> Decimal:
    """Available funds = total member payments − total invested (cannot allocate more than collected)."""
    return total_member_contributions_collected(verified_only=verified_only) - total_invested_across_investments(
        exclude_investment_id=exclude_investment_id
    )


def project_invested_total(project_id: int, exclude_investment_id: int | None = None) -> Decimal:
    """Sum of total_amount_invested for investments linked to this project."""
    q = db.session.query(func.coalesce(func.sum(Investment.total_amount_invested), 0)).filter(
        Investment.project_id == project_id
    )
    if exclude_investment_id is not None:
        q = q.filter(Investment.id != exclude_investment_id)
    v = q.scalar() or 0
    return Decimal(str(v))


def project_budget_headroom(project: Project, exclude_investment_id: int | None = None) -> Decimal | None:
    """Remaining budget before cap; None if project has no budget set."""
    if project.total_budget is None:
        return None
    budget = project.total_budget or Decimal("0")
    used = project_invested_total(project.id, exclude_investment_id=exclude_investment_id)
    return budget - used
