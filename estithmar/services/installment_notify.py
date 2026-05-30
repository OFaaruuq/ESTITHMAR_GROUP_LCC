"""Installment due / overdue / monthly payment reminders for members."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import render_template, url_for

from estithmar import db
from estithmar.models import (
    InstallmentPlan,
    InstallmentReminderLog,
    Member,
    NotificationDeliveryLog,
    ShareSubscription,
    get_or_create_settings,
)
from estithmar.services.email_html import brand_for_email, try_render_transactional
from estithmar.services.installments import (
    active_installment_rows,
    effective_row_due,
    installment_settings,
    is_row_overdue_for_display,
    recompute_all_active_installment_statuses,
    row_late_fee_amount,
    row_outstanding_balance,
)


def _ex() -> dict:
    return get_or_create_settings().get_extra()


def _should_notify(kind: str) -> bool:
    if not _ex().get("notify_members_enabled", True):
        return False
    return bool(_ex().get(f"notify_member_installment_{kind}", True))


def _fmt(sym: str, cur: str, d: Decimal) -> str:
    return f"{sym}{(d or Decimal('0')):,.2f} {cur}"


def _month_bounds(ref: date) -> tuple[date, date]:
    start = ref.replace(day=1)
    last_day = monthrange(ref.year, ref.month)[1]
    end = ref.replace(day=last_day)
    return start, end


def _installment_detail_rows(
    row: InstallmentPlan,
    sub: ShareSubscription,
    balance: Decimal,
    *,
    sym: str,
    cur: str,
    as_of: date,
) -> list[tuple[str, str]]:
    scheduled = effective_row_due(row, as_of=as_of, persist=False)
    paid = row.paid_amount or Decimal("0")
    base_due = row.due_amount or Decimal("0")
    fee = row_late_fee_amount(row, as_of=as_of)
    rows = [
        ("Subscription", str(sub.subscription_no)),
        ("Installment #", str(row.sequence_no)),
        ("Due date", str(row.due_date)),
        ("Scheduled amount", _fmt(sym, cur, base_due)),
    ]
    if fee > 0:
        rows.append(("Late fee", _fmt(sym, cur, fee)))
    rows.extend(
        [
            ("Total due (incl. fees)", _fmt(sym, cur, scheduled)),
            ("Already paid", _fmt(sym, cur, paid)),
            ("Balance to pay", _fmt(sym, cur, balance)),
            ("Subscription outstanding", _fmt(sym, cur, sub.outstanding_balance())),
        ]
    )
    return rows


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


def _monthly_sent_recently(member_id: int, *, as_of: datetime | None = None) -> bool:
    try:
        cooldown = max(1, int(_ex().get("installment_monthly_reminder_cooldown_days") or 28))
    except (TypeError, ValueError):
        cooldown = 28
    now = as_of or datetime.utcnow()
    since = now - timedelta(days=cooldown)
    logs = (
        NotificationDeliveryLog.query.filter(
            NotificationDeliveryLog.message_kind == "member_installment_monthly",
            NotificationDeliveryLog.success.is_(True),
            NotificationDeliveryLog.created_at >= since,
        )
        .order_by(NotificationDeliveryLog.created_at.desc())
        .limit(300)
        .all()
    )
    mid = str(member_id)
    for log in logs:
        if not log.context_json:
            continue
        try:
            ctx = json.loads(log.context_json)
        except Exception:
            continue
        if str(ctx.get("member_id")) == mid:
            return True
    return False


def _log_reminder(row_id: int, kind: str) -> None:
    db.session.add(InstallmentReminderLog(installment_plan_id=row_id, reminder_kind=kind))


def _notify_member(
    member: Member,
    *,
    subject: str,
    body: str,
    html: str,
    message_kind: str = "member_installment",
    context: dict | None = None,
) -> bool:
    if not (member.email and str(member.email).strip()):
        return False
    from estithmar.services.notifications import (
        _whatsapp_for_member_messages,
        mail_configured,
        notify_member_channel,
        send_email_with_retry,
        send_whatsapp_with_retry,
        whatsapp_configured,
    )

    email_to = member.email.strip()
    if message_kind == "member_installment_monthly":
        if not mail_configured():
            return False
        ok, _ = send_email_with_retry(
            email_to,
            subject,
            body,
            body_html=html,
            retries=2,
            message_kind=message_kind,
            context=context or {"member_id": member.id},
        )
        if (
            ok
            and member.phone
            and whatsapp_configured()
            and _whatsapp_for_member_messages()
            and _ex().get("notify_members_whatsapp")
        ):
            send_whatsapp_with_retry(
                member.phone,
                body.replace("\n", " ")[:1500],
                retries=1,
                message_kind=message_kind,
                context=context or {"member_id": member.id},
            )
        return bool(ok)

    notify_member_channel(
        email_to=email_to,
        phone=member.phone,
        subject=subject,
        body_text=body,
        body_html=html,
        send_whatsapp_too=True,
    )
    return True


def build_member_installment_reminder_payload(member: Member, *, as_of: date | None = None) -> dict | None:
    """Collect unpaid installment rows for a member (current month + overdue)."""
    today = as_of or date.today()
    month_start, month_end = _month_bounds(today)
    month_label = today.strftime("%B %Y")

    subs = (
        member.subscriptions.filter(
            ShareSubscription.payment_plan == "installment",
            ShareSubscription.status != "Cancelled",
        )
        .all()
    )
    if not subs:
        return None

    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    items: list[dict] = []
    total_balance = Decimal("0")
    total_this_month = Decimal("0")

    for sub in subs:
        for row in active_installment_rows(sub):
            balance = row_outstanding_balance(row, as_of=today)
            if balance <= 0:
                continue
            is_overdue = is_row_overdue_for_display(row, as_of=today)
            due_this_month = bool(
                row.due_date and month_start <= row.due_date <= month_end
            )
            if not is_overdue and not due_this_month:
                continue

            scheduled = effective_row_due(row, as_of=today, persist=False)
            paid = row.paid_amount or Decimal("0")
            items.append(
                {
                    "subscription_no": sub.subscription_no,
                    "subscription_id": sub.id,
                    "sequence_no": row.sequence_no,
                    "due_date": str(row.due_date),
                    "scheduled_amount": _fmt(sym, cur, scheduled),
                    "paid_amount": _fmt(sym, cur, paid),
                    "balance_due": _fmt(sym, cur, balance),
                    "balance_raw": balance,
                    "is_overdue": is_overdue,
                    "due_this_month": due_this_month,
                }
            )
            total_balance += balance
            if due_this_month or is_overdue:
                total_this_month += balance

    if not items:
        return None

    items.sort(key=lambda x: (0 if x["is_overdue"] else 1, x["due_date"]))
    return {
        "member": member,
        "items": items,
        "total_balance": _fmt(sym, cur, total_balance),
        "total_balance_raw": total_balance.quantize(Decimal("0.01")),
        "total_this_month": _fmt(sym, cur, total_this_month) if total_this_month > 0 else None,
        "total_this_month_raw": total_this_month.quantize(Decimal("0.01")),
        "month_label": month_label,
        "sym": sym,
        "cur": cur,
    }


def notify_member_installment_overdue(
    member: Member,
    sub: ShareSubscription,
    row: InstallmentPlan,
    balance: Decimal,
    *,
    as_of: date | None = None,
) -> bool:
    if not _should_notify("overdue"):
        return False
    today = as_of or date.today()
    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    sub_path = url_for("subscriptions_profile", id=sub.id, _external=True)
    name = member.full_name or member.member_id_display
    detail = _installment_detail_rows(row, sub, balance, sym=sym, cur=cur, as_of=today)
    subj = f"Installment overdue — pay {_fmt(sym, cur, balance)} — {sub.subscription_no}"
    body = (
        f"Hello {name},\n\n"
        f"Installment #{row.sequence_no} on subscription {sub.subscription_no} is overdue.\n"
        f"Balance to pay: {_fmt(sym, cur, balance)}\n"
        f"Please pay as soon as possible to avoid additional late fees.\n\n"
        f"View subscription: {sub_path}\n"
    )
    html = try_render_transactional(
        audience="Member",
        title="Installment overdue — payment required",
        intro=(
            f"Hello {name},\n\n"
            f"An installment on your subscription is past due. "
            f"The balance you need to pay is {_fmt(sym, cur, balance)}."
        ),
        detail_rows=detail,
        cta_url=sub_path,
        cta_label="View subscription & schedule",
        secondary_note="Please pay on time to keep your subscription in good standing.",
    )
    return _notify_member(member, subject=subj, body=body, html=html or "")


def notify_member_installment_upcoming(
    member: Member,
    sub: ShareSubscription,
    row: InstallmentPlan,
    balance: Decimal,
    *,
    as_of: date | None = None,
) -> bool:
    if not _should_notify("upcoming"):
        return False
    today = as_of or date.today()
    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    sub_path = url_for("subscriptions_profile", id=sub.id, _external=True)
    name = member.full_name or member.member_id_display
    detail = _installment_detail_rows(row, sub, balance, sym=sym, cur=cur, as_of=today)
    subj = f"Installment due soon — {_fmt(sym, cur, balance)} — {sub.subscription_no}"
    body = (
        f"Hello {name},\n\n"
        f"Installment #{row.sequence_no} on subscription {sub.subscription_no} "
        f"is due on {row.due_date}.\n"
        f"Balance to pay: {_fmt(sym, cur, balance)}\n\n"
        f"Please pay on time to avoid late fees.\n\n"
        f"View subscription: {sub_path}\n"
    )
    html = try_render_transactional(
        audience="Member",
        title="Installment due soon — pay on time",
        intro=(
            f"Hello {name},\n\n"
            f"You have an upcoming installment due on {row.due_date}. "
            f"The amount to pay is {_fmt(sym, cur, balance)}."
        ),
        detail_rows=detail,
        cta_url=sub_path,
        cta_label="View subscription & schedule",
        secondary_note="Pay before the due date to avoid late fees.",
    )
    return _notify_member(member, subject=subj, body=body, html=html or "")


def notify_member_installment_monthly_reminder(member: Member, payload: dict) -> bool:
    """Consolidated monthly email: installments due this month + overdue, with balances."""
    if not _should_notify("monthly"):
        return False

    name = member.full_name or member.member_id_display
    month_label = payload["month_label"]
    total_balance = payload["total_balance"]
    total_this_month = payload.get("total_this_month")
    items = payload["items"]

    portal_url = None
    try:
        portal_url = url_for("reports_installments", _external=True)
    except Exception:
        pass

    subj = f"Monthly payment reminder — {total_balance} due — {month_label}"
    lines = [
        f"Hello {name},",
        "",
        f"This is your payment reminder for {month_label}.",
        f"Total balance to pay: {total_balance}",
    ]
    if total_this_month:
        lines.append(f"Amount due this month (incl. overdue): {total_this_month}")
    lines.extend(["", "Installment details:", ""])
    for item in items:
        status = "OVERDUE" if item["is_overdue"] else "Due"
        lines.append(
            f"- {item['subscription_no']} #{item['sequence_no']} · {item['due_date']} · "
            f"{status} · Balance: {item['balance_due']}"
        )
    lines.extend(["", "Please pay on or before each due date.", ""])
    if portal_url:
        lines.append(f"View your schedule: {portal_url}")
    body = "\n".join(lines)

    b = brand_for_email()
    intro = (
        f"Hello {name},\n\n"
        f"Please pay your installment(s) on time for {month_label}. "
        f"Your total balance to pay is {total_balance}."
    )
    if total_this_month:
        intro += f"\n\nDue this month (including overdue): {total_this_month}."

    try:
        html = render_template(
            "emails/member_installment_payment.html",
            org_name=b["org_name"],
            org_subtitle=b.get("org_subtitle") or "",
            footer_address=b.get("footer_address") or "",
            logo_src=b.get("logo_src"),
            title="Monthly payment reminder",
            intro=intro,
            month_label=month_label,
            total_balance=total_balance,
            total_this_month=total_this_month,
            items=items,
            cta_url=portal_url,
            cta_label="View my installments" if portal_url else None,
        )
    except Exception:
        html = try_render_transactional(
            audience="Member",
            title=f"Monthly payment reminder — {month_label}",
            intro=intro,
            detail_rows=[(it["subscription_no"] + " #" + str(it["sequence_no"]), it["balance_due"]) for it in items],
            cta_url=portal_url,
            cta_label="View my installments" if portal_url else None,
            secondary_note=f"Total balance to pay: {total_balance}",
        )

    return _notify_member(
        member,
        subject=subj,
        body=body,
        html=html or "",
        message_kind="member_installment_monthly",
        context={"member_id": member.id, "month": month_label},
    )


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
                if notify_member_installment_overdue(member, sub, row, bal, as_of=today):
                    _log_reminder(row.id, "overdue")
                    sent_overdue += 1
                else:
                    skipped += 1
            elif row.due_date and row.due_date <= today + timedelta(days=cfg["reminder_days_ahead"]):
                if _reminder_sent_recently(row.id, "upcoming"):
                    skipped += 1
                    continue
                if notify_member_installment_upcoming(member, sub, row, bal, as_of=today):
                    _log_reminder(row.id, "upcoming")
                    sent_upcoming += 1
                else:
                    skipped += 1
        except Exception:
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


def run_monthly_member_installment_reminders(*, as_of: date | None = None, force: bool = False) -> dict:
    """Send one consolidated monthly payment reminder per member with installment balances."""
    if not force and not _should_notify("monthly"):
        return {"sent": 0, "skipped": 0, "failed": 0, "empty": 0, "aborted": True}

    today = as_of or date.today()
    recompute_all_active_installment_statuses(commit=True)

    sent = skipped = failed = empty = 0
    member_ids = (
        db.session.query(Member.id)
        .join(ShareSubscription, ShareSubscription.member_id == Member.id)
        .filter(
            ShareSubscription.payment_plan == "installment",
            ShareSubscription.status != "Cancelled",
            Member.status == "Active",
        )
        .distinct()
        .all()
    )

    for (mid,) in member_ids:
        member = db.session.get(Member, mid)
        if not member or not (member.email or "").strip():
            skipped += 1
            continue
        try:
            payload = build_member_installment_reminder_payload(member, as_of=today)
            if not payload:
                empty += 1
                continue
            if not force and _monthly_sent_recently(member.id):
                skipped += 1
                continue
            if notify_member_installment_monthly_reminder(member, payload):
                sent += 1
            else:
                skipped += 1
        except Exception:
            from flask import current_app

            current_app.logger.exception("Monthly installment reminder failed for member %s", mid)
            failed += 1

    db.session.commit()
    return {"sent": sent, "skipped": skipped, "failed": failed, "empty": empty, "aborted": False}
