"""Installment due / overdue reminders for members."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import url_for

from estithmar import db
from estithmar.models import InstallmentPlan, InstallmentReminderLog, Member, ShareSubscription, get_or_create_settings
from estithmar.services.email_html import try_render_transactional
from estithmar.services.installments import (
    effective_row_due,
    installment_settings,
    is_row_overdue_for_display,
    recompute_all_active_installment_statuses,
    row_outstanding_balance,
)


def _should_notify(kind: str) -> bool:
    ex = get_or_create_settings().get_extra()
    if not ex.get("notify_members_enabled", True):
        return False
    return bool(ex.get(f"notify_member_installment_{kind}", True))


def _reminder_sent_recently(row_id: int, kind: str, *, as_of: datetime | None = None) -> bool:
    cfg = installment_settings()
    cooldown = max(1, int(cfg.get("reminder_cooldown_days") or 1))
    now = as_of or datetime.utcnow()
    since = now - timedelta(days=cooldown)
    return (
        InstallmentReminderLog.query.filter(
            InstallmentReminderLog.installment_plan_id == row_id,
            InstallmentReminderLog.reminder_kind == kind,
            InstallmentReminderLog.sent_at >= since,
        )
        .limit(1)
        .first()
        is not None
    )


def _log_reminder(row_id: int, kind: str) -> None:
    db.session.add(InstallmentReminderLog(installment_plan_id=row_id, reminder_kind=kind))


def _notify_member(member: Member, *, subject: str, body: str, html: str) -> bool:
    if not (member.email and str(member.email).strip()):
        return False
    from estithmar.services.notifications import notify_member_channel

    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subject,
        body_text=body,
        body_html=html,
        send_whatsapp_too=True,
    )
    return True


def notify_member_installment_overdue(
    member: Member,
    sub: ShareSubscription,
    row: InstallmentPlan,
    balance: Decimal,
) -> bool:
    if not _should_notify("overdue"):
        return False
    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    sub_path = url_for("subscriptions_profile", id=sub.id, _external=True)
    name = member.full_name or member.member_id_display
    subj = f"Installment overdue — {sub.subscription_no}"
    body = (
        f"Hello {name},\n\n"
        f"Installment #{row.sequence_no} on subscription {sub.subscription_no} is overdue.\n"
        f"Due date: {row.due_date}\n"
        f"Balance due: {sym}{balance:,.2f} {cur}\n\n"
        f"View subscription: {sub_path}\n"
    )
    html = try_render_transactional(
        audience="Member",
        title="Installment overdue",
        intro=f"Hello {name},\n\nAn installment on your subscription is past due.",
        detail_rows=[
            ("Subscription", str(sub.subscription_no)),
            ("Installment #", str(row.sequence_no)),
            ("Due date", str(row.due_date)),
            ("Balance due", f"{sym}{balance:,.2f} {cur}"),
        ],
        cta_url=sub_path,
        cta_label="View subscription",
    )
    return _notify_member(member, subject=subj, body=body, html=html)


def notify_member_installment_upcoming(
    member: Member,
    sub: ShareSubscription,
    row: InstallmentPlan,
    balance: Decimal,
) -> bool:
    if not _should_notify("upcoming"):
        return False
    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    sub_path = url_for("subscriptions_profile", id=sub.id, _external=True)
    name = member.full_name or member.member_id_display
    subj = f"Installment due soon — {sub.subscription_no}"
    body = (
        f"Hello {name},\n\n"
        f"Installment #{row.sequence_no} on subscription {sub.subscription_no} is due on {row.due_date}.\n"
        f"Amount due: {sym}{balance:,.2f} {cur}\n\n"
        f"View subscription: {sub_path}\n"
    )
    html = try_render_transactional(
        audience="Member",
        title="Installment due soon",
        intro=f"Hello {name},\n\nYou have an upcoming installment on your subscription.",
        detail_rows=[
            ("Subscription", str(sub.subscription_no)),
            ("Installment #", str(row.sequence_no)),
            ("Due date", str(row.due_date)),
            ("Amount due", f"{sym}{balance:,.2f} {cur}"),
        ],
        cta_url=sub_path,
        cta_label="View subscription",
    )
    return _notify_member(member, subject=subj, body=body, html=html)


def run_installment_reminders(*, as_of: date | None = None) -> dict:
    """Send overdue and upcoming-due installment reminders (respects cooldown)."""
    today = as_of or date.today()
    cfg = installment_settings()
    recompute_all_active_installment_statuses(commit=True)

    sent_overdue = sent_upcoming = skipped = failed = 0
    rows = (
        InstallmentPlan.query.join(ShareSubscription)
        .join(Member, ShareSubscription.member_id == Member.id)
        .filter(
            ShareSubscription.payment_plan == "installment",
            ShareSubscription.status != "Cancelled",
            InstallmentPlan.status != "Cancelled",
        )
        .all()
    )

    for row in rows:
        sub = row.subscription
        member = sub.member if sub else None
        if not member:
            skipped += 1
            continue
        bal = row_outstanding_balance(row, as_of=today)
        if bal <= 0:
            continue
        try:
            if is_row_overdue_for_display(row, as_of=today):
                if _reminder_sent_recently(row.id, "overdue"):
                    skipped += 1
                    continue
                if notify_member_installment_overdue(member, sub, row, bal):
                    _log_reminder(row.id, "overdue")
                    sent_overdue += 1
                else:
                    skipped += 1
            elif row.due_date and row.due_date <= today + timedelta(days=cfg["reminder_days_ahead"]):
                if _reminder_sent_recently(row.id, "upcoming"):
                    skipped += 1
                    continue
                if notify_member_installment_upcoming(member, sub, row, bal):
                    _log_reminder(row.id, "upcoming")
                    sent_upcoming += 1
                else:
                    skipped += 1
        except Exception as exc:
            from flask import current_app

            current_app.logger.exception("Installment reminder failed for row %s", getattr(row, "id", None))
            failed += 1

    db.session.commit()
    return {
        "sent_overdue": sent_overdue,
        "sent_upcoming": sent_upcoming,
        "skipped": skipped,
        "failed": failed,
    }
