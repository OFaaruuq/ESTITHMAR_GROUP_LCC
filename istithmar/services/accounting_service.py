"""
Post double-entry journals from operational events (contributions, deployments,
profit recognition, capital return, profit distributions).

Posting targets accounts by stable ``system_key`` (see ``Account.system_key``).
Default codes/names are seeded once; administrators may change codes while keys stay fixed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError

from istithmar import db
from istithmar.accounting_models import Account, JournalEntry, JournalLine
from istithmar.models import Contribution, Investment, ProfitDistributionBatch, get_or_create_settings

# Stable identifiers for seeded / system accounts (not amounts — used for lookup only).
KEY_CASH = "cash"
KEY_MEMBER_FUNDS = "member_funds_liability"
KEY_DEPLOYED = "deployed_assets"
KEY_UNDISTRIBUTED_PROFIT = "undistributed_profit"
KEY_INVESTMENT_INCOME = "investment_income"
KEY_DISTRIBUTION_EXPENSE = "profit_distribution_expense"

# Default seed rows: (system_key, default_code, name, account_type, sort_order)
DEFAULT_SYSTEM_ACCOUNTS: tuple[tuple[str, str, str, str, int], ...] = (
    (KEY_CASH, "1000", "Cash and bank equivalents", "asset", 10),
    (KEY_MEMBER_FUNDS, "2000", "Member funds held (pool liability)", "liability", 20),
    (KEY_DEPLOYED, "4000", "Deployed investments (assets)", "asset", 30),
    (KEY_UNDISTRIBUTED_PROFIT, "5000", "Undistributed profit (liability)", "liability", 40),
    (KEY_INVESTMENT_INCOME, "6000", "Investment income (profit recognized)", "revenue", 50),
    (KEY_DISTRIBUTION_EXPENSE, "6100", "Profit distributions to members", "expense", 60),
)

# Legacy code → system_key (existing DBs created before system_key existed)
LEGACY_CODE_TO_KEY: dict[str, str] = {
    "1000": KEY_CASH,
    "2000": KEY_MEMBER_FUNDS,
    "4000": KEY_DEPLOYED,
    "5000": KEY_UNDISTRIBUTED_PROFIT,
    "6000": KEY_INVESTMENT_INCOME,
    "6100": KEY_DISTRIBUTION_EXPENSE,
}

SYSTEM_ACCOUNT_KEYS: frozenset[str] = frozenset(k for k, _, _, _, _ in DEFAULT_SYSTEM_ACCOUNTS)


def _ensure_account_system_key_column() -> None:
    """Add ``system_key`` to ``accounts`` when upgrading an older database."""
    insp = inspect(db.engine)
    if not insp.has_table("accounts"):
        return
    cols = {c["name"] for c in insp.get_columns("accounts")}
    if "system_key" in cols:
        return
    dialect = db.engine.dialect.name
    stmt = "ALTER TABLE accounts ADD COLUMN system_key VARCHAR(64) NULL"
    if dialect == "mssql":
        stmt = "ALTER TABLE accounts ADD system_key VARCHAR(64) NULL"
    with db.engine.begin() as conn:
        conn.execute(text(stmt))
    # Unique index (multiple NULLs allowed on most backends)
    idx = "CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_system_key ON accounts (system_key)"
    if dialect == "mssql":
        idx = (
            "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_accounts_system_key' "
            "AND object_id = OBJECT_ID('accounts')) "
            "CREATE UNIQUE INDEX ix_accounts_system_key ON accounts (system_key) "
            "WHERE system_key IS NOT NULL"
        )
    try:
        with db.engine.begin() as conn:
            conn.execute(text(idx))
    except Exception:
        pass


def _backfill_system_keys_from_legacy_codes() -> None:
    for acc in Account.query.filter(Account.system_key.is_(None)).all():
        if acc.code in LEGACY_CODE_TO_KEY:
            acc.system_key = LEGACY_CODE_TO_KEY[acc.code]
    db.session.flush()


def account_by_system_key(key: str) -> Account | None:
    return Account.query.filter_by(system_key=key).first()


def accounting_enabled() -> bool:
    return get_or_create_settings().get_extra().get("accounting_enabled", True) is True


def ensure_chart_of_accounts() -> None:
    """Idempotent seed: create missing system accounts and attach legacy codes. Does not commit."""
    _ensure_account_system_key_column()
    _backfill_system_keys_from_legacy_codes()

    existing_keys = {r.system_key for r in Account.query.filter(Account.system_key.isnot(None)).all() if r.system_key}
    for system_key, default_code, name, atype, sort in DEFAULT_SYSTEM_ACCOUNTS:
        if system_key in existing_keys:
            continue
        row = Account.query.filter_by(code=default_code).first()
        if row is not None and row.system_key is None:
            row.system_key = system_key
            row.name = row.name or name
            db.session.flush()
            existing_keys.add(system_key)
            continue
        if Account.query.filter_by(code=default_code).first() is not None:
            # Code collision: create with suffixed code
            suffix = 1
            while Account.query.filter_by(code=f"{default_code}-{suffix}").first() is not None:
                suffix += 1
            default_code = f"{default_code}-{suffix}"
        db.session.add(
            Account(
                code=default_code,
                system_key=system_key,
                name=name,
                account_type=atype,
                sort_order=sort,
                is_active=True,
            )
        )
        db.session.flush()


def _balance_entry(lines: list[tuple[Account, Decimal, Decimal, str]]) -> bool:
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
    """lines_spec: (system_key, debit, credit, description)."""
    ensure_chart_of_accounts()
    accts: list[tuple[Account, Decimal, Decimal, str]] = []
    for skey, dr, cr, desc in lines_spec:
        a = account_by_system_key(skey)
        if a is None or not a.is_active:
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
        delete_entries_for_source("contribution", contribution_id)
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
            (KEY_CASH, amt, Decimal("0"), "Cash in"),
            (KEY_MEMBER_FUNDS, Decimal("0"), amt, "Member funds liability"),
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
            (KEY_DEPLOYED, delta, Decimal("0"), f"Deploy +{delta}"),
            (KEY_MEMBER_FUNDS, Decimal("0"), delta, "Pool applied to investment"),
        ]
    else:
        d = abs(delta)
        lines = [
            (KEY_MEMBER_FUNDS, d, Decimal("0"), "Reversal / reduction"),
            (KEY_DEPLOYED, Decimal("0"), d, "Deploy adjustment"),
        ]
    je = _add_entry(
        date.today(),
        f"INV-{ref}",
        f"Deployment delta for {inv.name}"[:500],
        "investment_deploy",
        investment_id,
        lines,
        user_id,
    )
    return je is not None


def post_profit_recognition_delta(
    investment_id: int,
    old_profit: Decimal,
    new_profit: Decimal,
    *,
    user_id: int | None,
    entry_date: date | None = None,
) -> bool:
    """
    When ``profit_generated`` changes: recognize investment income vs deployed assets.

    Positive delta: Dr Deployed assets, Cr Investment income (revenue).
    Negative delta: reverse (Dr Investment income, Cr Deployed).
    """
    if not accounting_enabled():
        return False
    delta = (new_profit - old_profit).quantize(Decimal("0.01"))
    if delta == 0:
        return True
    inv = db.session.get(Investment, investment_id)
    if inv is None:
        return False
    ref = inv.investment_code or str(inv.id)
    d = entry_date or date.today()
    memo = f"Profit recognition investment_id={inv.id} {inv.name}"[:500]
    if delta > 0:
        lines = [
            (KEY_DEPLOYED, delta, Decimal("0"), "Unrealized / recognized profit (deployed)"),
            (KEY_INVESTMENT_INCOME, Decimal("0"), delta, "Investment income"),
        ]
    else:
        amt = abs(delta)
        lines = [
            (KEY_INVESTMENT_INCOME, amt, Decimal("0"), "Profit adjustment (reduction)"),
            (KEY_DEPLOYED, Decimal("0"), amt, "Deployed assets (reversal)"),
        ]
    je = _add_entry(
        d,
        f"PR-{ref}",
        memo,
        "profit_recognition",
        investment_id,
        lines,
        user_id,
    )
    return je is not None


def post_capital_return_delta(
    investment_id: int,
    old_returned: Decimal,
    new_returned: Decimal,
    *,
    user_id: int | None,
    entry_date: date | None = None,
) -> bool:
    """
    When ``capital_returned`` increases, cash is paid to members: Cr Cash, Dr Deployed (return of principal).

    Positive delta: Dr Deployed, Cr Cash.
    Negative delta: Dr Cash, Cr Deployed (reversal of recorded return).
    """
    if not accounting_enabled():
        return False
    delta = (new_returned - old_returned).quantize(Decimal("0.01"))
    if delta == 0:
        return True
    inv = db.session.get(Investment, investment_id)
    if inv is None:
        return False
    ref = inv.investment_code or str(inv.id)
    d = entry_date or date.today()
    memo = f"Capital return investment_id={inv.id} {inv.name}"[:500]
    if delta > 0:
        lines = [
            (KEY_DEPLOYED, delta, Decimal("0"), "Return of principal (deployed)"),
            (KEY_CASH, Decimal("0"), delta, "Cash paid to members"),
        ]
    else:
        amt = abs(delta)
        lines = [
            (KEY_CASH, amt, Decimal("0"), "Capital return reversal (cash)"),
            (KEY_DEPLOYED, Decimal("0"), amt, "Deployed assets (restored)"),
        ]
    je = _add_entry(
        d,
        f"CR-{ref}",
        memo,
        "capital_return",
        investment_id,
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
        delete_entries_for_source("profit_batch", batch_id)
        return False
    delete_entries_for_source("profit_batch", batch_id)
    je = _add_entry(
        b.distribution_date,
        b.batch_no or f"PB-{batch_id}",
        f"Profit batch investment_id={b.investment_id}",
        "profit_batch",
        batch_id,
        [
            (KEY_DISTRIBUTION_EXPENSE, amt, Decimal("0"), "Profit distribution"),
            (KEY_CASH, Decimal("0"), amt, "Cash / transfer to members"),
        ],
        user_id,
    )
    return je is not None


def trial_balance_rows() -> list[dict[str, Any]]:
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
                "system_key": a.system_key,
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
    ("profit_recognition", "Profit recognition"),
    ("capital_return", "Capital return"),
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


def gl_posting_error_message(exc: BaseException) -> str:
    """User-safe message; log full exception in caller."""
    if isinstance(exc, IntegrityError):
        return "General ledger posting failed (database constraint). Check chart of accounts."
    return f"General ledger posting failed: {exc!s}"

