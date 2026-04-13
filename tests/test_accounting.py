"""Accounting GL: opening balance, ledger, void manual entry."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from estithmar import db
from estithmar.accounting_models import Account, JournalEntry, JournalLine
from estithmar.services.accounting_service import (
    KEY_DEPLOYED,
    KEY_INVESTMENT_INCOME,
    account_by_system_key,
    account_net_balance_before,
    ensure_chart_of_accounts,
    ledger_lines_for_account,
    post_profit_recognition_delta,
    void_manual_journal_entry,
)
from estithmar.models import Investment


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


def test_profit_recognition_journal_balances(app):
    with app.app_context():
        ensure_chart_of_accounts()
        db.session.commit()
        deployed = account_by_system_key(KEY_DEPLOYED)
        income = account_by_system_key(KEY_INVESTMENT_INCOME)
        assert deployed is not None and income is not None
        inv = Investment(
            name="GL test inv",
            investment_code="INV-TEST-GL-1",
            total_amount_invested=Decimal("5000.00"),
            profit_generated=Decimal("0"),
            status="Active",
        )
        db.session.add(inv)
        db.session.commit()
        ok = post_profit_recognition_delta(
            inv.id, Decimal("0"), Decimal("250.00"), user_id=None
        )
        assert ok
        db.session.commit()
        opening_d, lines_d = ledger_lines_for_account(deployed.id, limit=50)
        opening_i, lines_i = ledger_lines_for_account(income.id, limit=50)
        assert len(lines_d) >= 1 and len(lines_i) >= 1
        assert lines_d[-1]["debit"] == Decimal("250.00")
        assert lines_i[-1]["credit"] == Decimal("250.00")
