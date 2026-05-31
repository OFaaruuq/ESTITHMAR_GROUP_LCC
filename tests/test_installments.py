"""Tests for installment allocation, status, and schedule helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from estithmar import db
from estithmar.models import Contribution, InstallmentPlan, Member, ShareSubscription, get_or_create_settings
from estithmar.services.certificates import issue_certificate
from estithmar.services.installments import (
    allocate_contribution_to_installments,
    reschedule_remaining_balance,
    reschedule_remaining_balance_preview,
    cleanup_and_rebuild_installment_schedule,
    cancel_unpaid_installment_rows,
    ensure_installment_schedule_exists,
    generate_installment_schedule,
    is_row_overdue_for_display,
    rebalance_installment_due_amounts,
    recompute_installment_statuses,
    normalize_installment_sequences,
    next_installment_sequence_no,
    has_duplicate_installment_sequences,
    regenerate_future_installment_schedule,
    schedule_health_warnings,
    shift_installment_due_dates,
    should_allocate_contribution,
    subscription_schedule_adherence,
    subscription_schedule_gap,
    summarize_installment_rows,
    sync_orphan_payments_to_installments,
    unallocate_contribution_from_installments,
    validate_sequence_no,
    waive_installment_late_fee,
)
from estithmar.services.subscriptions import create_subscription


@pytest.fixture
def member_and_sub(app):
    with app.app_context():
        m = Member(
            member_id="EST-9001",
            full_name="Installment Test Member",
            status="Active",
        )
        db.session.add(m)
        db.session.flush()
        sub = create_subscription(
            member_id=m.id,
            share_units=10,
            payment_plan="installment",
            commit=False,
        )
        db.session.commit()
        yield m, sub
        db.session.query(InstallmentPlan).delete()
        db.session.query(Contribution).delete()
        db.session.query(ShareSubscription).delete()
        db.session.query(Member).delete()
        db.session.commit()


def test_generate_and_allocate_fifo(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        generate_installment_schedule(
            sub.id,
            installments_count=2,
            frequency="monthly",
            start_date=date(2026, 1, 1),
            commit=True,
        )
        rows = sub.installments.order_by(InstallmentPlan.sequence_no).all()
        assert len(rows) == 2
        c = Contribution(
            member_id=m.id,
            subscription_id=sub.id,
            amount=Decimal("100.00"),
            date=date.today(),
            payment_type="Cash",
            receipt_no="R-INST-1",
        )
        db.session.add(c)
        db.session.flush()
        allocate_contribution_to_installments(c, commit=True)
        rows = sub.installments.order_by(InstallmentPlan.sequence_no).all()
        assert rows[0].status in {"Fully Paid", "Partially Paid"}
        assert (rows[0].paid_amount or Decimal("0")) > 0


def test_partial_overdue_status(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2020, 1, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("40"),
            status="Partially Paid",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.commit()
        recompute_installment_statuses(sub.id, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert row.status == "Overdue"
        assert is_row_overdue_for_display(row)


def test_require_schedule_blocks_payment(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_require_schedule"] = True
        settings.set_extra(ex)
        db.session.commit()
        with pytest.raises(ValueError, match="no schedule"):
            ensure_installment_schedule_exists(sub)


def test_summarize_respects_grace(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_grace_days"] = 30
        settings.set_extra(ex)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date.today(),
            due_amount=Decimal("100"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.commit()
        sm = summarize_installment_rows([row], as_of=date.today())
        assert sm["overdue_count"] == 0


def test_sync_orphan_payments(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        generate_installment_schedule(
            sub.id,
            installments_count=2,
            frequency="monthly",
            start_date=date(2026, 1, 1),
            commit=True,
        )
        c = Contribution(
            member_id=m.id,
            subscription_id=sub.id,
            amount=Decimal("50.00"),
            date=date.today(),
            payment_type="Cash",
            receipt_no="R-INST-3",
            verified=True,
        )
        db.session.add(c)
        db.session.flush()
        allocate_contribution_to_installments(c, commit=True)
        synced = sync_orphan_payments_to_installments(sub.id, commit=True)
        assert synced >= Decimal("0")


def test_adherence_no_double_count(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        generate_installment_schedule(
            sub.id,
            installments_count=2,
            frequency="monthly",
            start_date=date(2026, 1, 1),
            commit=True,
        )
        adh = subscription_schedule_adherence(sub)
        assert adh["total_rows"] == 2
        assert adh["fully_paid"] + adh["overdue"] + adh["pending_future"] + adh["partial"] <= adh["total_rows"]


def test_unverify_unallocates(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date.today(),
            due_amount=Decimal("200"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.flush()
        c = Contribution(
            member_id=m.id,
            subscription_id=sub.id,
            amount=Decimal("50"),
            date=date.today(),
            payment_type="Cash",
            receipt_no="R-INST-2",
        )
        db.session.add(c)
        db.session.flush()
        allocate_contribution_to_installments(c, commit=True)
        assert (row.paid_amount or Decimal("0")) == Decimal("50")
        unallocate_contribution_from_installments(c, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert (row.paid_amount or Decimal("0")) == Decimal("0")


def test_schedule_gap(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        db.session.add(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=date.today(),
                due_amount=sub.subscribed_amount - Decimal("10"),
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=1,
            )
        )
        db.session.commit()
        gap = subscription_schedule_gap(sub)
        assert gap["schedule_gap"] == Decimal("10.00")


def test_late_fee_in_balance(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_late_fee_fixed"] = "25"
        ex["installment_grace_days"] = 0
        settings.set_extra(ex)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2020, 1, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.commit()
        recompute_installment_statuses(sub.id, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert row.late_fee_amount == Decimal("25.00")
        assert row.balance() == Decimal("125.00")


def test_late_fee_after_principal_paid(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_late_fee_fixed"] = "25"
        ex["installment_grace_days"] = 0
        settings.set_extra(ex)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2020, 1, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("100"),
            status="Partially Paid",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.commit()
        recompute_installment_statuses(sub.id, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert row.balance() == Decimal("25.00")


def test_unallocate_skips_when_never_allocated(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date.today(),
            due_amount=Decimal("200"),
            paid_amount=Decimal("50"),
            status="Partially Paid",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.flush()
        c = Contribution(
            member_id=m.id,
            subscription_id=sub.id,
            amount=Decimal("50"),
            date=date.today(),
            payment_type="Cash",
            receipt_no="R-NOALLOC",
            verified=False,
        )
        db.session.add(c)
        db.session.flush()
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_allocate_on_verify"] = True
        settings.set_extra(ex)
        db.session.commit()
        unallocate_contribution_from_installments(c, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert (row.paid_amount or Decimal("0")) == Decimal("50")


def test_allocate_on_verify(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_allocate_on_verify"] = True
        settings.set_extra(ex)
        db.session.add(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=date.today(),
                due_amount=Decimal("200"),
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=1,
            )
        )
        db.session.commit()
        c = Contribution(
            member_id=m.id,
            subscription_id=sub.id,
            amount=Decimal("50"),
            date=date.today(),
            payment_type="Cash",
            receipt_no="R-INST-VERIFY",
            verified=False,
        )
        db.session.add(c)
        db.session.flush()
        assert not should_allocate_contribution(c)
        allocate_contribution_to_installments(c, commit=True)
        row = sub.installments.first()
        assert (row.paid_amount or Decimal("0")) == Decimal("0")
        c.verified = True
        allocate_contribution_to_installments(c, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert (row.paid_amount or Decimal("0")) == Decimal("50")


def test_certificate_blocked_without_schedule(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_require_schedule"] = True
        settings.set_extra(ex)
        sub.status = "Fully Paid"
        sub.confirmed_at = None
        db.session.add(
            Contribution(
                member_id=m.id,
                subscription_id=sub.id,
                amount=sub.subscribed_amount,
                date=date.today(),
                payment_type="Cash",
                receipt_no="R-FULL",
                verified=True,
            )
        )
        db.session.commit()
        with pytest.raises(ValueError, match="schedule"):
            issue_certificate(sub.id, commit=False)


def test_rebalance_closes_gap(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        db.session.add(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=date(2026, 1, 1),
                due_amount=sub.subscribed_amount - Decimal("20"),
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=1,
            )
        )
        db.session.commit()
        assert subscription_schedule_gap(sub)["schedule_gap"] == Decimal("20.00")
        rebalance_installment_due_amounts(sub.id, commit=True)
        assert abs(subscription_schedule_gap(sub)["schedule_gap"]) <= Decimal("0.01")


def test_validate_sequence_no_duplicate(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        db.session.add(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=date(2026, 1, 1),
                due_amount=Decimal("100"),
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=1,
            )
        )
        db.session.commit()
        with pytest.raises(ValueError, match="Sequence #1"):
            validate_sequence_no(sub, 1)


def test_normalize_installment_sequences_fixes_duplicates(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        for due, seq in (
            (date(2026, 1, 1), 1),
            (date(2026, 2, 1), 1),
            (date(2026, 3, 1), 2),
            (date(2026, 4, 1), 2),
        ):
            db.session.add(
                InstallmentPlan(
                    subscription_id=sub.id,
                    due_date=due,
                    due_amount=Decimal("50"),
                    paid_amount=Decimal("0"),
                    status="Pending",
                    sequence_no=seq,
                )
            )
        db.session.commit()
        assert has_duplicate_installment_sequences(sub)
        changed = normalize_installment_sequences(sub.id, commit=True)
        assert changed == 4
        sub = db.session.get(ShareSubscription, sub.id)
        active = [r for r in sub.installments.all() if r.status != "Cancelled"]
        active.sort(key=lambda r: r.due_date)
        assert [r.sequence_no for r in active] == [1, 2, 3, 4]
        assert not has_duplicate_installment_sequences(sub)
        assert next_installment_sequence_no(sub) == 5


def test_shift_dates(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2026, 3, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.commit()
        n = shift_installment_due_dates(sub.id, 7, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert n == 1
        assert row.due_date == date(2026, 3, 8)


def test_regenerate_future_keeps_paid(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        paid_row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2026, 1, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("100"),
            status="Fully Paid",
            sequence_no=1,
        )
        unpaid_row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2026, 2, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=2,
        )
        db.session.add_all([paid_row, unpaid_row])
        db.session.commit()
        new_rows = regenerate_future_installment_schedule(
            sub.id,
            installments_count=2,
            frequency="monthly",
            start_date=date(2026, 4, 1),
            commit=True,
        )
        paid_row = db.session.get(InstallmentPlan, paid_row.id)
        unpaid_row = db.session.get(InstallmentPlan, unpaid_row.id)
        assert paid_row.status != "Cancelled"
        assert unpaid_row.status == "Cancelled"
        assert len(new_rows) == 2
        active = [r for r in sub.installments.all() if r.status != "Cancelled"]
        active.sort(key=lambda r: r.due_date)
        assert [r.sequence_no for r in active] == [1, 2, 3]
        assert not has_duplicate_installment_sequences(sub)


def test_regenerate_start_date_after_kept_rows(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        kept = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2026, 6, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("50"),
            status="Partially Paid",
            sequence_no=1,
        )
        db.session.add(kept)
        db.session.commit()
        regenerate_future_installment_schedule(
            sub.id,
            installments_count=1,
            frequency="monthly",
            start_date=date(2026, 4, 1),
            commit=True,
        )
        new_rows = [r for r in sub.installments.all() if r.status == "Pending" and r.id != kept.id]
        assert new_rows
        assert new_rows[0].due_date > kept.due_date


def test_cancel_unpaid_rows(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        r1 = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2026, 1, 1),
            due_amount=Decimal("50"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=1,
        )
        r2 = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2026, 2, 1),
            due_amount=Decimal("50"),
            paid_amount=Decimal("25"),
            status="Partially Paid",
            sequence_no=2,
        )
        db.session.add_all([r1, r2])
        db.session.commit()
        n = cancel_unpaid_installment_rows(sub.id, commit=True)
        r1 = db.session.get(InstallmentPlan, r1.id)
        r2 = db.session.get(InstallmentPlan, r2.id)
        assert n == 1
        assert r1.status == "Cancelled"
        assert r2.status != "Cancelled"
        assert r2.sequence_no == 1


def test_reschedule_remaining_keeps_paid_months(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        subscribed = sub.subscribed_amount or Decimal("1000")
        per_month = (subscribed / Decimal("10")).quantize(Decimal("0.01"))
        rows = []
        for i in range(1, 11):
            paid = per_month if i <= 2 else Decimal("0")
            rows.append(
                InstallmentPlan(
                    subscription_id=sub.id,
                    due_date=date(2026, i, 1),
                    due_amount=per_month,
                    paid_amount=paid,
                    status="Fully Paid" if paid >= per_month else "Pending",
                    sequence_no=i,
                )
            )
        db.session.add_all(rows)
        db.session.commit()

        preview = reschedule_remaining_balance_preview(sub, installments_count=4)
        assert preview["locked_count"] == 2
        assert preview["rows_to_remove"] == 8
        assert preview["remaining_balance"] == subscribed - (per_month * 2)

        result = reschedule_remaining_balance(
            sub.id,
            installments_count=4,
            frequency="monthly",
            start_date=date(2026, 3, 1),
            commit=True,
        )
        assert result["locked_count"] == 2
        assert result["removed"] == 8
        assert result["created"] == 4
        paid_rows = [
            r for r in sub.installments.all()
            if r.status != "Cancelled" and (r.paid_amount or Decimal("0")) > 0
        ]
        assert len(paid_rows) == 2
        assert all(r.paid_amount == per_month for r in paid_rows)
        assert abs(result["schedule_gap"]) <= Decimal("0.01")


def test_cleanup_and_rebuild_installment_schedule(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        for due, seq, paid in (
            (date(2026, 1, 1), 1, Decimal("0")),
            (date(2026, 1, 1), 1, Decimal("0")),
            (date(2026, 2, 1), 2, Decimal("100")),
            (date(2026, 3, 1), 2, Decimal("0")),
        ):
            db.session.add(
                InstallmentPlan(
                    subscription_id=sub.id,
                    due_date=due,
                    due_amount=Decimal("100"),
                    paid_amount=paid,
                    status="Fully Paid" if paid >= Decimal("100") else "Pending",
                    sequence_no=seq,
                )
            )
        db.session.commit()
        result = cleanup_and_rebuild_installment_schedule(
            sub.id,
            installments_count=2,
            frequency="monthly",
            start_date=date(2026, 4, 1),
            commit=True,
        )
        assert result["removed"] == 3
        assert result["created"] == 2
        assert result["locked_count"] == 1
        active = [r for r in sub.installments.all() if r.status != "Cancelled"]
        active.sort(key=lambda r: r.due_date)
        assert [r.sequence_no for r in active] == [1, 2, 3]
        assert abs(result["schedule_gap"]) <= Decimal("0.01")


def test_generate_auto_rebalance_closes_gap(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        generate_installment_schedule(
            sub.id,
            installments_count=2,
            frequency="monthly",
            start_date=date(2026, 1, 1),
            commit=True,
        )
        assert abs(subscription_schedule_gap(sub)["schedule_gap"]) <= Decimal("0.01")


def test_waive_late_fee(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        settings = get_or_create_settings()
        ex = settings.get_extra()
        ex["installment_late_fee_fixed"] = "25"
        ex["installment_grace_days"] = 0
        settings.set_extra(ex)
        row = InstallmentPlan(
            subscription_id=sub.id,
            due_date=date(2020, 1, 1),
            due_amount=Decimal("100"),
            paid_amount=Decimal("0"),
            status="Pending",
            sequence_no=1,
        )
        db.session.add(row)
        db.session.commit()
        recompute_installment_statuses(sub.id, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert row.balance() == Decimal("125.00")
        waive_installment_late_fee(row.id, sub.id, commit=True)
        row = db.session.get(InstallmentPlan, row.id)
        assert row.late_fee_waived is True
        assert row.balance() == Decimal("100.00")


def test_schedule_health_warnings_gap(app, member_and_sub):
    m, sub = member_and_sub
    with app.app_context():
        sub = db.session.get(ShareSubscription, sub.id)
        db.session.add(
            InstallmentPlan(
                subscription_id=sub.id,
                due_date=date.today(),
                due_amount=sub.subscribed_amount - Decimal("50"),
                paid_amount=Decimal("0"),
                status="Pending",
                sequence_no=1,
            )
        )
        db.session.commit()
        warnings = schedule_health_warnings(sub)
        assert any("under-subscribed" in w for w in warnings)
