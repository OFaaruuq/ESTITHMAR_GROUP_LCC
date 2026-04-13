"""Automatic email/WhatsApp to members for payments, subscriptions, profit, certificates."""

from __future__ import annotations

from decimal import Decimal
from flask import url_for

from estithmar.models import Contribution, Member, ShareCertificate, ShareSubscription, get_or_create_settings


def _ex() -> dict:
    return get_or_create_settings().get_extra()


def should_notify(kind: str) -> bool:
    """
    kind: payment | subscription | profit | certificate
    """
    ex = _ex()
    if not ex.get("notify_members_enabled", True):
        return False
    return bool(ex.get(f"notify_member_{kind}", True))


def notify_member_payment(contribution: Contribution, member: Member) -> None:
    if not should_notify("payment"):
        return
    if not (member.email and str(member.email).strip()):
        return
    from estithmar.services.notifications import notify_member_channel

    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    amt = contribution.amount or Decimal("0")
    receipt_path = url_for("contributions_receipt", id=contribution.id, _external=True)
    subj = f"Payment recorded — {sym}{amt:,.2f} {cur}"
    body = (
        f"Hello {member.full_name or member.member_id},\n\n"
        f"A payment of {sym}{amt:,.2f} {cur} has been recorded on {contribution.date}.\n"
        f"Receipt / reference: {contribution.receipt_no or contribution.id}\n"
        f"Method: {contribution.payment_display_label()}\n\n"
        f"View receipt: {receipt_path}\n\n"
        "This is an automated message from Estithmar."
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        send_whatsapp_too=True,
    )


def notify_member_new_subscription(sub: ShareSubscription, member: Member) -> None:
    if not should_notify("subscription"):
        return
    if not (member.email and str(member.email).strip()):
        return
    from estithmar.services.notifications import notify_member_channel

    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    sub_path = url_for("subscriptions_profile", id=sub.id, _external=True)
    amt = sub.subscribed_amount or Decimal("0")
    subj = f"Share subscription created — {sub.subscription_no or sub.id}"
    body = (
        f"Hello {member.full_name or member.member_id},\n\n"
        f"A share subscription was created: {sub.subscription_no or sub.id}\n"
        f"Subscribed amount: {sym}{amt:,.2f} {cur}\n"
        f"Status: {sub.status}\n\n"
        f"View subscription: {sub_path}\n\n"
        "This is an automated message from Estithmar."
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        send_whatsapp_too=True,
    )


def notify_member_profit_share(
    member: Member,
    *,
    amount: Decimal,
    investment_name: str,
    batch_no: str | None,
    distribution_date,
) -> None:
    if not should_notify("profit"):
        return
    if not (member.email and str(member.email).strip()):
        return
    from estithmar.services.notifications import notify_member_channel

    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    stmt_path = url_for("profit_statement", member_id=member.id, _external=True)
    subj = f"Profit distribution — {sym}{amount:,.2f} {cur}"
    body = (
        f"Hello {member.full_name or member.member_id},\n\n"
        f"A profit share of {sym}{amount:,.2f} {cur} has been allocated to you.\n"
        f"Investment: {investment_name}\n"
        f"Batch: {batch_no or '—'}\n"
        f"Distribution date: {distribution_date}\n\n"
        f"View statement: {stmt_path}\n\n"
        "This is an automated message from Estithmar."
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        send_whatsapp_too=True,
    )


def notify_member_certificate_issued(cert: ShareCertificate, member: Member) -> None:
    if not should_notify("certificate"):
        return
    if not (member.email and str(member.email).strip()):
        return
    from estithmar.services.notifications import notify_member_channel

    print_path = url_for("certificates_print", id=cert.id, _external=True)
    subj = f"Share certificate issued — {cert.certificate_no or cert.id}"
    body = (
        f"Hello {member.full_name or member.member_id},\n\n"
        f"A share certificate has been issued: {cert.certificate_no or cert.id}\n"
        f"Issue date: {cert.issued_date}\n\n"
        f"View / print: {print_path}\n\n"
        "This is an automated message from Estithmar."
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        send_whatsapp_too=True,
    )
