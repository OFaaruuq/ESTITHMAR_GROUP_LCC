"""Shared report query builders and scheduled-report email summaries."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from flask import url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from estithmar import db
from estithmar.models import (
    Agent,
    Contribution,
    Investment,
    Member,
    PaymentBankAccount,
    PaymentMobileProvider,
    ProfitDistribution,
    ShareSubscription,
    get_or_create_settings,
)
from estithmar.services.agent_collections import collect_agent_overdue_members, summarize_agent_overdue
from estithmar.services.installments import (
    installment_plans_scope_query,
    recompute_all_active_installment_statuses,
    summarize_installment_rows,
)


def _sym_cur() -> tuple[str, str]:
    s = get_or_create_settings()
    return s.currency_symbol or "$", s.currency_code or "USD"


def _fmt_money(d: Decimal) -> str:
    sym, cur = _sym_cur()
    return f"{sym}{(d or Decimal('0')):,.2f} {cur}"


def monthly_contribution_rows(
    *,
    year: int,
    month: int,
    agent_id: int | None = None,
    scope_agent_id: int | None = None,
) -> tuple[list[Contribution], Decimal, date, date]:
    start = date(year, month, 1)
    end = start + relativedelta(months=1) - relativedelta(days=1)
    q = Contribution.query.filter(Contribution.date >= start, Contribution.date <= end).join(Member)
    if scope_agent_id:
        q = q.filter(Member.agent_id == scope_agent_id)
    elif agent_id:
        q = q.filter(Member.agent_id == agent_id)
    rows = (
        q.options(
            joinedload(Contribution.member).joinedload(Member.agent),
            joinedload(Contribution.payment_bank_account).joinedload(PaymentBankAccount.bank),
            joinedload(Contribution.payment_mobile_provider),
        )
        .order_by(Contribution.date.desc(), Contribution.id.desc())
        .all()
    )
    total = sum((r.amount or Decimal("0") for r in rows), Decimal("0"))
    return rows, total.quantize(Decimal("0.01")), start, end


def daily_contribution_rows(
    *,
    report_date: date,
    scope_agent_id: int | None = None,
) -> tuple[list[Contribution], Decimal]:
    q = Contribution.query.filter(Contribution.date == report_date).join(Member)
    if scope_agent_id:
        q = q.filter(Member.agent_id == scope_agent_id)
    rows = (
        q.options(
            joinedload(Contribution.member).joinedload(Member.agent),
            joinedload(Contribution.payment_bank_account).joinedload(PaymentBankAccount.bank),
            joinedload(Contribution.payment_mobile_provider),
        )
        .order_by(Contribution.id.desc())
        .all()
    )
    total = sum((r.amount or Decimal("0") for r in rows), Decimal("0"))
    return rows, total.quantize(Decimal("0.01"))


def members_financial_rows(
    *,
    member_query,
    status_filter: str = "",
    only_outstanding: bool = False,
) -> tuple[list[dict], dict]:
    q = member_query.options(joinedload(Member.agent))
    if status_filter in ("Active", "Inactive"):
        q = q.filter(Member.status == status_filter)
    members = q.order_by(Member.member_id.asc()).all()
    rows: list[dict] = []
    agg = {
        "subscribed": Decimal("0"),
        "paid": Decimal("0"),
        "outstanding": Decimal("0"),
        "confirmed_value": Decimal("0"),
        "confirmed_units": Decimal("0"),
        "profit": Decimal("0"),
    }
    for m in members:
        subs = m.subscriptions.filter(ShareSubscription.status != "Cancelled").all()
        t_sub = sum((s.subscribed_amount or Decimal("0") for s in subs), Decimal("0"))
        t_paid = sum((s.paid_total() for s in subs), Decimal("0"))
        out = sum((s.outstanding_balance() for s in subs), Decimal("0"))
        conf_v = sum(
            (s.subscribed_amount or Decimal("0") for s in subs if s.status == "Fully Paid"),
            Decimal("0"),
        )
        conf_u = sum(
            (s.share_units_subscribed or Decimal("0") for s in subs if s.status == "Fully Paid"),
            Decimal("0"),
        )
        if only_outstanding and out <= 0:
            continue
        pt = m.lifetime_profit_received()
        rows.append(
            {
                "member": m,
                "subscribed": t_sub,
                "paid": t_paid,
                "outstanding": out,
                "confirmed_value": conf_v,
                "confirmed_units": conf_u,
                "profit": pt,
            }
        )
        agg["subscribed"] += t_sub
        agg["paid"] += t_paid
        agg["outstanding"] += out
        agg["confirmed_value"] += conf_v
        agg["confirmed_units"] += conf_u
        agg["profit"] += pt
    return rows, agg


def build_scheduled_report_summary(report_key: str) -> tuple[str, list[tuple[str, str]], str | None]:
    """Build intro text, detail rows, and optional deep-link URL for scheduled report emails."""
    key = (report_key or "").strip()
    today = date.today()
    sym, cur = _sym_cur()
    detail: list[tuple[str, str]] = []
    cta: str | None = None

    try:
        if key == "reports_monthly":
            y, m = today.year, today.month
            _, total, start, end = monthly_contribution_rows(year=y, month=m)
            detail = [
                ("Period", f"{start} — {end}"),
                ("Contributions (count)", str(
                    Contribution.query.filter(
                        Contribution.date >= start, Contribution.date <= end
                    ).count()
                )),
                ("Total collected", _fmt_money(total)),
            ]
            cta = url_for("reports_monthly", year=y, month=m, _external=True)
            intro = f"Monthly contribution summary for {start.strftime('%B %Y')}.\n\nTotal collected: {_fmt_money(total)}."
            return intro, detail, cta

        if key == "reports_daily":
            rows, total = daily_contribution_rows(report_date=today)
            detail = [
                ("Date", str(today)),
                ("Receipts", str(len(rows))),
                ("Total collected", _fmt_money(total)),
            ]
            cta = url_for("reports_daily", date=today.isoformat(), _external=True)
            intro = f"Daily collection summary for {today}.\n\nTotal collected: {_fmt_money(total)}."
            return intro, detail, cta

        if key == "reports_members_financial":
            rows, agg = members_financial_rows(member_query=Member.query, only_outstanding=False)
            detail = [
                ("Members", str(len(rows))),
                ("Subscribed", _fmt_money(agg["subscribed"])),
                ("Paid", _fmt_money(agg["paid"])),
                ("Outstanding", _fmt_money(agg["outstanding"])),
            ]
            cta = url_for("reports_members_financial", _external=True)
            intro = (
                f"Members financial snapshot.\n\n"
                f"Outstanding across members: {_fmt_money(agg['outstanding'])}."
            )
            return intro, detail, cta

        if key == "reports_profit_summary":
            inv_rows = Investment.query.order_by(Investment.name).all()
            total_gen = Decimal("0")
            total_dist = Decimal("0")
            total_undist = Decimal("0")
            for inv in inv_rows:
                dist_total = (
                    db.session.query(func.coalesce(func.sum(ProfitDistribution.amount), 0))
                    .filter(ProfitDistribution.investment_id == inv.id)
                    .scalar()
                    or 0
                )
                generated = inv.profit_generated or Decimal("0")
                distributed = Decimal(str(dist_total))
                undistributed = max(generated - distributed, Decimal("0"))
                total_gen += generated
                total_dist += distributed
                total_undist += undistributed
            detail = [
                ("Investments", str(len(inv_rows))),
                ("Profit generated", _fmt_money(total_gen)),
                ("Distributed", _fmt_money(total_dist)),
                ("Undistributed", _fmt_money(total_undist)),
            ]
            cta = url_for("reports_profit_summary", _external=True)
            intro = f"Profit summary.\n\nUndistributed profit: {_fmt_money(total_undist)}."
            return intro, detail, cta

        if key == "reports_investment_summary":
            invs = Investment.query.all()
            invested = sum((i.total_amount_invested or Decimal("0") for i in invs), Decimal("0"))
            profit = sum((i.profit_generated or Decimal("0") for i in invs), Decimal("0"))
            detail = [
                ("Investments", str(len(invs))),
                ("Total deployed", _fmt_money(invested)),
                ("Profit generated", _fmt_money(profit)),
            ]
            cta = url_for("reports_investment_summary", _external=True)
            intro = f"Investment deployment summary.\n\nTotal deployed: {_fmt_money(invested)}."
            return intro, detail, cta

        if key == "reports_installments":
            recompute_all_active_installment_statuses(commit=True)
            rows = installment_plans_scope_query().all()
            sm = summarize_installment_rows(rows, as_of=today)
            detail = [
                ("Overdue rows", str(sm["overdue_count"])),
                ("Open balance", _fmt_money(sm["due_balance"])),
                ("Active rows", str(sm["active_count"])),
            ]
            cta = url_for("reports_installments", _external=True)
            intro = (
                f"Installment health.\n\n"
                f"{sm['overdue_count']} overdue row(s); open balance {_fmt_money(sm['due_balance'])}."
            )
            return intro, detail, cta

        if key == "reports_overdue_members":
            summary = summarize_agent_overdue(None, as_of=today)
            detail = [
                ("Members overdue", str(summary["member_count"])),
                ("Overdue rows", str(summary["overdue_row_count"])),
                ("Overdue balance", _fmt_money(summary["overdue_balance"])),
            ]
            cta = url_for("collections_overdue_members", _external=True)
            intro = (
                f"Overdue members call list.\n\n"
                f"{summary['member_count']} member(s) with overdue installments."
            )
            return intro, detail, cta

    except Exception:
        pass

    intro = (
        f"Scheduled report key: {key or '(none)'}\n\n"
        "Open the Reports hub in Estithmar for the full on-screen report."
    )
    detail = [("Report key", key or "—"), ("Generated (UTC)", str(datetime.utcnow()))]
    try:
        cta = url_for("reports_hub", _external=True)
    except Exception:
        cta = None
    return intro, detail, cta
