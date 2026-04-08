"""
Post double-entry journals from operational events (contributions, deployments, profit batches).
Uses seeded chart of accounts; amounts in organization currency.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from istithmar import db
from istithmar.accounting_models import Account, JournalEntry, JournalLine
from istithmar.models import Contribution, Investment, ProfitDistributionBatch, get_or_create_settings

# Default account codes (seeded)
ACC_CASH = "1000"
ACC_MEMBER_FUNDS = "2000"
ACC_DEPLOYED = "4000"
ACC_DIST_EXPENSE = "6100"

# Seeded / system accounts — do not deactivate (posting depends on these codes).
SYSTEM_ACCOUNT_CODES: frozenset[str] = frozenset(
    {"1000", "2000", "4000", "5000", "6000", "6100"}
)


def _account_by_code(code: str) -> Account | None:
    return Account.query.filter_by(code=code).first()


def ensure_chart_of_accounts() -> None:
    """Idempotent seed of minimal accounts for Istithmar pool / deployment / distributions."""
    rows = [
        (ACC_CASH, "Cash and bank equivalents", "asset", 10),
        (ACC_MEMBER_FUNDS, "Member funds held (pool liability)", "liability", 20),
        (ACC_DEPLOYED, "Deployed investments (assets)", "asset", 30),
        ("5000", "Undistributed profit (liability)", "liability", 40),
        ("6000", "Investment income (profit recognized)", "revenue", 50),
        (ACC_DIST_EXPENSE, "Profit distributions to members", "expense", 60),
    ]
    for code, name, atype, sort in rows:
        if Account.query.filter_by(code=code).first() is None:
            db.session.add(
                Account(code=code, name=name, account_type=atype, sort_order=sort, is_active=True)
            )
    db.session.commit()  # seed once


def accounting_enabled() -> bool:
    return get_or_create_settings().get_extra().get("accounting_enabled", True) is True


def _balance_entry(lines: list[tuple[Account, Decimal, Decimal, str]]) -> bool:
    """lines: (account, debit, credit, desc). Returns True if debits == credits."""
    td = sum((d for _, d, _, _ in lines), Decimal("0"))
    tc = sum((c for _, _, c, _ in lines), Decimal("0"))
    return (td - tc).quantize(Decimal("0.01")) == Decimal("0")


def _add_entry(
    entry_date: date,
    reference: str,
    memo: str,
    source_type: str,
    source_id: int | None,
    lines_spec: list[tuple[str, Decimal, Decimal, str]],
    user_id: int | None,
) -> JournalEntry | None:
    """lines_spec: (account_code, debit, credit, description)."""
    ensure_chart_of_accounts()
    accts: list[tuple[Account, Decimal, Decimal, str]] = []
    for code, dr, cr, desc in lines_spec:
        a = _account_by_code(code)
        if a is None:
            return None
        accts.append((a, dr, cr, desc))
    if not _balance_entry(accts):
        return None
    je = JournalEntry(
        entry_date=entry_date,
        reference=reference[:64] if reference else None,
        memo=(memo or "")[:500] or None,
        source_type=source_type,
        source_id=source_id,
        status="posted",
        created_by_user_id=user_id,
    )
    db.session.add(je)
    db.session.flush()
    for i, (acc, dr, cr, desc) in enumerate(accts, start=1):
        db.session.add(
            JournalLine(
                journal_entry_id=je.id,
                account_id=acc.id,
                debit=dr,
                credit=cr,
                description=(desc or "")[:300] or None,
                line_no=i,
            )
        )
    return je


def delete_entries_for_source(source_type: str, source_id: int) -> int:
    """Remove journal entries by source (e.g. unverify contribution). Returns count deleted."""
    q = JournalEntry.query.filter_by(source_type=source_type, source_id=source_id)
    n = 0
    for je in q.all():
        JournalLine.query.filter_by(journal_entry_id=je.id).delete()
        db.session.delete(je)
        n += 1
    return n


def post_contribution_verified(contribution_id: int, *, user_id: int | None) -> bool:
    """Dr Cash, Cr Member funds. Idempotent: replaces prior entry for same contribution."""
    if not accounting_enabled():
        return False
    c = db.session.get(Contribution, contribution_id)
    if c is None or not c.verified:
        delete_entries_for_source("contribution", contribution_id)
        return False
    amt = Decimal(str(c.amount or 0))
    if amt <= 0:
        return False
    delete_entries_for_source("contribution", contribution_id)
    memo = f"Contribution {c.receipt_no or c.id} member_id={c.member_id}"
    je = _add_entry(
        c.date,
        f"REC-{c.receipt_no or c.id}",
        memo,
        "contribution",
        contribution_id,
        [
            (ACC_CASH, amt, Decimal("0"), "Cash in"),
            (ACC_MEMBER_FUNDS, Decimal("0"), amt, "Member funds liability"),
        ],
        user_id,
    )
    return je is not None


def post_contribution_unverified(contribution_id: int) -> None:
    if not accounting_enabled():
        return
    delete_entries_for_source("contribution", contribution_id)


def post_investment_deployment_delta(
    investment_id: int,
    old_deployed: Decimal,
    new_deployed: Decimal,
    *,
    user_id: int | None,
) -> bool:
    """
    When total_amount_invested changes: Dr Deployed, Cr Member funds for positive delta
    (funds move from pooled liability into deployed assets).
    """
    if not accounting_enabled():
        return False
    delta = (new_deployed - old_deployed).quantize(Decimal("0.01"))
    if delta == 0:
        return True
    inv = db.session.get(Investment, investment_id)
    if inv is None:
        return False
    ref = inv.investment_code or str(inv.id)
    if delta > 0:
        lines = [
            (ACC_DEPLOYED, delta, Decimal("0"), f"Deploy +{delta}"),
            (ACC_MEMBER_FUNDS, Decimal("0"), delta, "Pool applied to investment"),
        ]
    else:
        d = abs(delta)
        lines = [
            (ACC_MEMBER_FUNDS, d, Decimal("0"), "Reversal / reduction"),
            (ACC_DEPLOYED, Decimal("0"), d, "Deploy adjustment"),
        ]
    je = _add_entry(
        date.today(),
        f"INV-{ref}",
        f"Deployment delta for {inv.name}"[:500],
        "investment_deploy",
        None,
        lines,
        user_id,
    )
    return je is not None


def post_profit_distribution_batch(batch_id: int, *, user_id: int | None) -> bool:
    """Dr Distribution expense, Cr Cash (cash paid to members)."""
    if not accounting_enabled():
        return False
    b = db.session.get(ProfitDistributionBatch, batch_id)
    if b is None:
        return False
    amt = Decimal(str(b.total_profit_distributed or 0))
    if amt <= 0:
        return False
    delete_entries_for_source("profit_batch", batch_id)
    je = _add_entry(
        b.distribution_date,
        b.batch_no or f"PB-{batch_id}",
        f"Profit batch investment_id={b.investment_id}",
        "profit_batch",
        batch_id,
        [
            (ACC_DIST_EXPENSE, amt, Decimal("0"), "Profit distribution"),
            (ACC_CASH, Decimal("0"), amt, "Cash / transfer to members"),
        ],
        user_id,
    )
    return je is not None


def trial_balance_rows() -> list[dict[str, Any]]:
    """Sum debits/credits per account for posted entries."""
    ensure_chart_of_accounts()
    out = []
    for a in Account.query.order_by(Account.sort_order, Account.code).all():
        sums = (
            db.session.query(
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .select_from(JournalLine)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .filter(
                JournalLine.account_id == a.id,
                JournalEntry.status == "posted",
            )
            .first()
        )
        dr = Decimal(str(sums[0] or 0))
        cr = Decimal(str(sums[1] or 0))
        out.append(
            {
                "account_id": a.id,
                "code": a.code,
                "name": a.name,
                "type": a.account_type,
                "debit": dr,
                "credit": cr,
                "balance": dr - cr,
            }
        )
    return out


def journal_entries_list(limit: int = 200) -> list[JournalEntry]:
    return (
        JournalEntry.query.filter_by(status="posted")
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .limit(limit)
        .all()
    )


JOURNAL_SOURCE_TYPES: list[tuple[str | None, str]] = [
    (None, "All sources"),
    ("contribution", "Contributions"),
    ("investment_deploy", "Investment deployment"),
    ("profit_batch", "Profit distribution"),
    ("manual", "Manual entries"),
    ("opening", "Opening balance"),
]


def journal_entries_filtered(
    *,
    limit: int = 400,
    date_from: date | None = None,
    date_to: date | None = None,
    source_type: str | None = None,
) -> list[JournalEntry]:
    q = JournalEntry.query.filter_by(status="posted")
    if date_from is not None:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to is not None:
        q = q.filter(JournalEntry.entry_date <= date_to)
    if source_type:
        q = q.filter(JournalEntry.source_type == source_type)
    return (
        q.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).limit(limit).all()
    )


def account_net_balance_before(account_id: int, before_date: date) -> Decimal:
    """Net Dr-Cr for posted lines on journal entries strictly before before_date (opening for period starting before_date)."""
    sums = (
        db.session.query(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .filter(
            JournalLine.account_id == account_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date < before_date,
        )
        .first()
    )
    dr = Decimal(str(sums[0] or 0))
    cr = Decimal(str(sums[1] or 0))
    return (dr - cr).quantize(Decimal("0.01"))


def ledger_lines_for_account(
    account_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 1000,
) -> tuple[Decimal, list[dict[str, Any]]]:
    """Chronological lines for one account with running balance (Dr − Cr).
    When date_from is set, running balance starts from opening balance (all posted activity before that date).
    Returns (opening_balance, lines).
    """
    ensure_chart_of_accounts()
    opening = account_net_balance_before(account_id, date_from) if date_from is not None else Decimal("0")
    q = (
        db.session.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .filter(JournalLine.account_id == account_id, JournalEntry.status == "posted")
    )
    if date_from is not None:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to is not None:
        q = q.filter(JournalEntry.entry_date <= date_to)
    rows = (
        q.order_by(
            JournalEntry.entry_date.asc(),
            JournalEntry.id.asc(),
            JournalLine.line_no.asc(),
        )
        .limit(limit)
        .all()
    )
    running = opening
    out: list[dict[str, Any]] = []
    for jl, je in rows:
        dr = Decimal(str(jl.debit or 0))
        cr = Decimal(str(jl.credit or 0))
        running = (running + dr - cr).quantize(Decimal("0.01"))
        out.append(
            {
                "line_id": jl.id,
                "entry_id": je.id,
                "entry_date": je.entry_date,
                "reference": je.reference,
                "memo": je.memo,
                "source_type": je.source_type,
                "source_id": je.source_id,
                "debit": dr,
                "credit": cr,
                "running_balance": running,
                "line_description": jl.description,
            }
        )
    return opening, out


def void_manual_journal_entry(entry_id: int) -> tuple[bool, str]:
    """Mark a manual journal as void; excludes it from trial balance and reports."""
    je = db.session.get(JournalEntry, entry_id)
    if je is None:
        return False, "Journal entry not found."
    if je.status != "posted":
        return False, "Only posted entries can be voided."
    if je.source_type != "manual":
        return False, "Only manual entries can be voided (system postings are reversed at source)."
    je.status = "void"
    return True, ""


def lines_for_entry(je_id: int) -> list[JournalLine]:
    return (
        JournalLine.query.filter_by(journal_entry_id=je_id)
        .order_by(JournalLine.line_no)
        .all()
    )
