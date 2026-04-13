"""General ledger: chart of accounts and double-entry journal (integrates with operations)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Index, text

from estithmar import db


class Account(db.Model):
    """Chart of accounts.

    ``system_key`` identifies accounts used by automated postings (cash, member pool,
    deployed assets, etc.). Codes and names may be renamed; keys stay stable.

    Uniqueness of ``system_key`` uses a filtered unique index on SQL Server (multiple NULLs
    are allowed). A plain UNIQUE index on a nullable column fails on MSSQL with duplicate NULL.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        Index(
            "ix_accounts_system_key",
            "system_key",
            unique=True,
            mssql_where=text("system_key IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    system_key = db.Column(db.String(64), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(
        db.String(20), nullable=False
    )  # asset, liability, equity, revenue, expense
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class JournalEntry(db.Model):
    """Header for a balanced journal entry."""

    __tablename__ = "journal_entries"

    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.Date, nullable=False, default=date.today)
    reference = db.Column(db.String(64))
    memo = db.Column(db.String(500))
    # contribution | investment_deploy | profit_batch | profit_recognition | capital_return | manual | opening
    source_type = db.Column(db.String(40), nullable=True, index=True)
    source_id = db.Column(db.Integer, nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="posted")  # posted, void
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)

    lines = db.relationship(
        "JournalLine",
        backref="entry",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="JournalLine.line_no",
    )
    created_by = db.relationship("AppUser", foreign_keys=[created_by_user_id], viewonly=False)


class JournalLine(db.Model):
    """Debit/credit line."""

    __tablename__ = "journal_lines"

    id = db.Column(db.Integer, primary_key=True)
    journal_entry_id = db.Column(
        db.Integer, db.ForeignKey("journal_entries.id"), nullable=False, index=True
    )
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    debit = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    credit = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    description = db.Column(db.String(300))
    line_no = db.Column(db.Integer, nullable=False, default=1)

    account = db.relationship("Account", backref=db.backref("lines", lazy="dynamic"))
