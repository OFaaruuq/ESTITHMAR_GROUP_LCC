"""Automatic email/WhatsApp to members for payments, subscriptions, profit, certificates."""

from __future__ import annotations

from decimal import Decimal
from flask import url_for

from estithmar.models import Contribution, Member, ShareCertificate, ShareSubscription, get_or_create_settings
from estithmar.services.email_html import try_render_transactional


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
    name = member.full_name or member.member_id_display
    subj = f"Payment recorded — {sym}{amt:,.2f} {cur}"
    body = (
        f"Hello {name},\n\n"
        f"A payment of {sym}{amt:,.2f} {cur} has been recorded on {contribution.date}.\n"
        f"Receipt / reference: {contribution.receipt_no or contribution.id}\n"
        f"Method: {contribution.payment_display_label()}\n\n"
        f"View receipt: {receipt_path}\n\n"
        "This is an automated message from Estithmar."
    )
    intro = (
        f"Hello {name},\n\n"
        f"We've recorded a payment to your account. Details are below."
    )
    html = try_render_transactional(
        audience="Member",
        title="Payment recorded",
        intro=intro,
        detail_rows=[
            ("Amount", f"{sym}{amt:,.2f} {cur}"),
            ("Date", str(contribution.date)),
            ("Receipt / reference", str(contribution.receipt_no or contribution.id)),
            ("Method", str(contribution.payment_display_label() or "—")),
        ],
        cta_url=receipt_path,
        cta_label="View official receipt",
        secondary_note="Keep this email for your records. If anything looks wrong, contact your office.",
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        body_html=html,
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
    name = member.full_name or member.member_id_display
    subj = f"Share subscription created — {sub.subscription_no or sub.id}"
    body = (
        f"Hello {name},\n\n"
        f"A share subscription was created: {sub.subscription_no or sub.id}\n"
        f"Subscribed amount: {sym}{amt:,.2f} {cur}\n"
        f"Status: {sub.status}\n\n"
        f"View subscription: {sub_path}\n\n"
        "This is an automated message from Estithmar."
    )
    intro = (
        f"Hello {name},\n\n"
        f"Your new share subscription is in the system. You can follow progress and payment history in the member portal."
    )
    html = try_render_transactional(
        audience="Member",
        title="Share subscription",
        intro=intro,
        detail_rows=[
            ("Subscription", str(sub.subscription_no or sub.id)),
            ("Subscribed amount", f"{sym}{amt:,.2f} {cur}"),
            ("Status", str(sub.status or "—")),
        ],
        cta_url=sub_path,
        cta_label="View subscription",
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        body_html=html,
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
    name = member.full_name or member.member_id_display
    subj = f"Profit distribution — {sym}{amount:,.2f} {cur}"
    body = (
        f"Hello {name},\n\n"
        f"A profit share of {sym}{amount:,.2f} {cur} has been allocated to you.\n"
        f"Investment: {investment_name}\n"
        f"Batch: {batch_no or '—'}\n"
        f"Distribution date: {distribution_date}\n\n"
        f"View statement: {stmt_path}\n\n"
        "This is an automated message from Estithmar."
    )
    intro = (
        f"Hello {name},\n\n"
        f"Great news: a new profit allocation has been credited to you from the following investment run."
    )
    html = try_render_transactional(
        audience="Member",
        title="Profit distribution",
        intro=intro,
        detail_rows=[
            ("Your allocation", f"{sym}{amount:,.2f} {cur}"),
            ("Investment", str(investment_name or "—")),
            ("Batch", str(batch_no or "—")),
            ("Distribution date", str(distribution_date or "—")),
        ],
        cta_url=stmt_path,
        cta_label="View member statement",
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        body_html=html,
        send_whatsapp_too=True,
    )


def notify_member_certificate_issued(cert: ShareCertificate, member: Member) -> None:
    if not should_notify("certificate"):
        return
    if not (member.email and str(member.email).strip()):
        return
    from estithmar.services.notifications import notify_member_channel

    print_path = url_for("certificates_print", id=cert.id, _external=True)
    name = member.full_name or member.member_id_display
    subj = f"Share certificate issued — {cert.certificate_no or cert.id}"
    body = (
        f"Hello {name},\n\n"
        f"A share certificate has been issued: {cert.certificate_no or cert.id}\n"
        f"Issue date: {cert.issued_date}\n\n"
        f"View / print: {print_path}\n\n"
        "This is an automated message from Estithmar."
    )
    intro = (
        f"Hello {name},\n\n"
        f"Your share certificate is ready. You can open, download, or print it from the link below."
    )
    html = try_render_transactional(
        audience="Member",
        title="Share certificate issued",
        intro=intro,
        detail_rows=[
            ("Certificate", str(cert.certificate_no or cert.id)),
            ("Issue date", str(cert.issued_date or "—")),
        ],
        cta_url=print_path,
        cta_label="View or print certificate",
    )
    notify_member_channel(
        email_to=member.email.strip(),
        phone=member.phone,
        subject=subj,
        body_text=body,
        body_html=html,
        send_whatsapp_too=True,
    )
