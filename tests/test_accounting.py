"""Accounting GL: opening balance, ledger, void manual entry."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from istithmar import db
from istithmar.accounting_models import Account, JournalEntry, JournalLine
from istithmar.services.accounting_service import (
    account_net_balance_before,
    ensure_chart_of_accounts,
    ledger_lines_for_account,
    void_manual_journal_entry,
)


def test_ledger_opening_balance_and_void_excludes_from_balance(app):
    with app.app_context():
        ensure_chart_of_accounts()
        cash = Account.query.filter_by(code="1000").first()
        liab = Account.query.filter_by(code="2000").first()
        je = JournalEntry(
            entry_date=date(2024, 1, 15),
            reference="T1",
            source_type="manual",
            status="posted",
        )
        db.session.add(je)
        db.session.flush()
        db.session.add(
            JournalLine(
                journal_entry_id=je.id,
                account_id=cash.id,
                debit=Decimal("100.00"),
                credit=Decimal("0"),
                line_no=1,
            )
        )
        db.session.add(
            JournalLine(
                journal_entry_id=je.id,
                account_id=liab.id,
                debit=Decimal("0"),
                credit=Decimal("100.00"),
                line_no=2,
            )
        )
        db.session.commit()

        assert account_net_balance_before(cash.id, date(2024, 2, 1)) == Decimal("100.00")
        opening, lines = ledger_lines_for_account(cash.id, date_from=date(2024, 2, 1))
        assert opening == Decimal("100.00")
        assert len(lines) == 0

        ok, msg = void_manual_journal_entry(je.id)
        assert ok, msg
        db.session.commit()

        assert account_net_balance_before(cash.id, date(2024, 2, 1)) == Decimal("0")
