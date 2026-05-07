"""Email official payment receipt PDF to the member."""

from __future__ import annotations

from decimal import Decimal

from flask import url_for

from estithmar.models import Contribution, Member, get_or_create_settings
from estithmar.services.email_html import try_render_transactional
from estithmar.services.notifications import mail_configured, send_email_with_retry


def send_contribution_receipt_pdf_to_member(
    *,
    contribution: Contribution,
    member: Member,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> tuple[bool, str | None]:
    to_email = (member.email or "").strip()
    if not to_email:
        return False, "Member has no email address."
    if not mail_configured():
        return False, "Mail is not configured (SMTP)."

    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    amt = contribution.amount or Decimal("0")
    receipt_path = url_for("contributions_receipt", id=contribution.id, _external=True)
    name = member.full_name or member.member_id_display
    subj = f"Payment receipt (PDF) — {sym}{amt:,.2f} {cur}"
    body = (
        f"Hello {name},\n\n"
        f"Please find your official payment receipt attached as a PDF ({pdf_filename}).\n\n"
        f"Amount: {sym}{amt:,.2f} {cur}\n"
        f"Date: {contribution.date}\n"
        f"Receipt / reference: {contribution.receipt_no or contribution.id}\n\n"
        f"View online: {receipt_path}\n\n"
        "This is an automated message from Estithmar."
    )
    intro = f"Hello {name},\n\nYour payment receipt is attached as a PDF for your records."
    html = try_render_transactional(
        audience="Member",
        title="Payment receipt (PDF attached)",
        intro=intro,
        detail_rows=[
            ("Amount", f"{sym}{amt:,.2f} {cur}"),
            ("Date", str(contribution.date)),
            ("Receipt / reference", str(contribution.receipt_no or contribution.id)),
        ],
        cta_url=receipt_path,
        cta_label="View receipt online",
        secondary_note="If you did not expect this message, contact your office.",
    )
    return send_email_with_retry(
        to_email,
        subj,
        body,
        body_html=html,
        attachments=[(pdf_filename, pdf_bytes, "application/pdf")],
        retries=2,
        message_kind="contribution_receipt_pdf",
        context={"contribution_id": contribution.id, "member_id": member.id},
    )
