"""Email (SMTP) and WhatsApp (Twilio) — environment and/or Settings → Notifications."""

from __future__ import annotations

import json
import os
import re
import smtplib
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app, has_request_context

from estithmar import db
from estithmar.models import NotificationDeliveryLog, ReportSchedule, get_or_create_settings
from estithmar.services.email_html import (
    ESTITHMAR_EMAIL_LOGO_CID,
    audience_for_role_label,
    brand_logo_local_path,
    login_url,
    try_render_transactional,
)


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _extra() -> dict:
    if not has_request_context():
        return {}
    try:
        return get_or_create_settings().get_extra()
    except Exception:
        return {}


def effective_smtp() -> dict[str, str | bool | None]:
    """Merge Settings (extra_json) with environment; non-empty settings override env."""
    ex = _extra()
    tls_raw = ex.get("smtp_use_tls")
    if tls_raw is None:
        tls_raw = os.environ.get("ESTITHMAR_MAIL_USE_TLS", "true")
    use_tls = str(tls_raw).strip().lower() not in ("0", "false", "no")
    port_raw = ex.get("smtp_port") or os.environ.get("ESTITHMAR_MAIL_PORT") or "587"
    try:
        port_int = int(port_raw)
    except (TypeError, ValueError):
        port_int = 587
    return {
        "host": (ex.get("smtp_host") or os.environ.get("ESTITHMAR_MAIL_SERVER") or "").strip(),
        "port": port_int,
        "use_tls": use_tls,
        "username": (ex.get("smtp_username") or os.environ.get("ESTITHMAR_MAIL_USERNAME") or "").strip(),
        "password": (
            ex.get("smtp_password")
            if ex.get("smtp_password") is not None
            else os.environ.get("ESTITHMAR_MAIL_PASSWORD")
        ),
        "sender": (ex.get("smtp_sender") or os.environ.get("ESTITHMAR_MAIL_SENDER") or "").strip(),
    }


def effective_twilio() -> dict[str, str]:
    ex = _extra()
    return {
        "sid": (ex.get("twilio_account_sid") or os.environ.get("TWILIO_ACCOUNT_SID") or "").strip(),
        "token": (ex.get("twilio_auth_token") or os.environ.get("TWILIO_AUTH_TOKEN") or "").strip(),
        "from": (ex.get("twilio_whatsapp_from") or os.environ.get("TWILIO_WHATSAPP_FROM") or "").strip(),
        "default_cc": (
            ex.get("whatsapp_default_cc") or os.environ.get("ESTITHMAR_WHATSAPP_DEFAULT_CC") or ""
        ).strip().lstrip("+"),
    }


def mail_configured() -> bool:
    c = effective_smtp()
    return bool(c["host"] and c["sender"])


def whatsapp_configured() -> bool:
    t = effective_twilio()
    return bool(t["sid"] and t["token"] and t["from"])


def send_email(
    to_addr: str,
    subject: str,
    body_text: str,
    *,
    body_html: str | None = None,
) -> tuple[bool, str | None]:
    c = effective_smtp()
    server = c["host"]
    if not server:
        return False, "Mail not configured (SMTP host)."
    sender = c["sender"]
    if not sender or not isinstance(sender, str):
        return False, "SMTP sender (From) is required."
    port = int(c["port"] or 587)
    use_tls = bool(c["use_tls"])
    user = (c["username"] or "").strip() if c["username"] else ""
    password = c["password"]
    if password is not None:
        password = str(password)

    def _image_part(logo_path: str) -> MIMEBase:
        with open(logo_path, "rb") as f:
            raw = f.read()
        ext = (os.path.splitext(logo_path)[1] or ".png").lower()
        if ext == ".svg":
            p = MIMEBase("image", "svg+xml")
            p.set_payload(raw)
            encoders.encode_base64(p)
            return p
        sub = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".jpe": "jpeg", ".gif": "gif", ".webp": "webp", ".bmp": "bmp"}.get(
            ext, "png"
        )
        try:
            return MIMEImage(raw, _subtype=sub)
        except Exception:
            p = MIMEBase("application", "octet-stream")
            p.set_payload(raw)
            encoders.encode_base64(p)
            return p

    def _html_without_broken_cid(html: str) -> str:
        return re.sub(
            r'(?is)<img\b[^>]*\ssrc\s*=\s*["\']' + re.escape(f"cid:{ESTITHMAR_EMAIL_LOGO_CID}") + r'["\'][^>]*>',
            "",
            html,
            count=1,
        )

    logo_path: str | None = None
    if body_html and f"cid:{ESTITHMAR_EMAIL_LOGO_CID}" in body_html:
        logo_path = brand_logo_local_path()
        if not logo_path or not os.path.isfile(logo_path):
            body_html = _html_without_broken_cid(body_html)
            logo_path = None

    if body_html and logo_path and f"cid:{ESTITHMAR_EMAIL_LOGO_CID}" in body_html:
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = str(sender)
        msg["To"] = to_addr
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain", "utf-8"))
        alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)
        part = _image_part(logo_path)
        part.add_header("Content-ID", f"<{ESTITHMAR_EMAIL_LOGO_CID}>")
        part.add_header("Content-Disposition", "inline", filename=os.path.basename(logo_path) or "logo")
        msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = str(sender)
        msg["To"] = to_addr
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password is not None and str(password) != "":
                smtp.login(user, str(password))
            elif user:
                smtp.login(user, "")
            smtp.sendmail(str(sender), [to_addr], msg.as_string())
    except Exception as exc:
        return False, str(exc)
    return True, None


def _log_delivery(
    *,
    channel: str,
    recipient: str,
    subject: str | None,
    message_kind: str | None,
    success: bool,
    attempt_count: int,
    error: str | None,
    context: dict | None = None,
) -> None:
    try:
        db.session.add(
            NotificationDeliveryLog(
                channel=channel,
                recipient=(recipient or "")[:200],
                subject=(subject or "")[:200] if subject else None,
                message_kind=(message_kind or "")[:40] if message_kind else None,
                success=bool(success),
                attempt_count=max(1, int(attempt_count)),
                error=(error or "")[:500] if error else None,
                context_json=json.dumps(context or {}),
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def phone_to_whatsapp_address(normalized_phone: str | None) -> str | None:
    if not normalized_phone:
        return None
    raw = normalized_phone.strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    tw = effective_twilio()
    cc = tw["default_cc"]
    if raw.startswith("+"):
        e164 = "+" + digits
    elif cc:
        e164 = "+" + cc + digits
    else:
        e164 = "+" + digits
    return f"whatsapp:{e164}"


def send_whatsapp_text(to_phone_normalized: str, message: str) -> tuple[bool, str | None]:
    tw = effective_twilio()
    sid, token, from_ = tw["sid"], tw["token"], tw["from"]
    if not (sid and token and from_):
        return False, "Twilio WhatsApp not configured."

    to = phone_to_whatsapp_address(to_phone_normalized)
    if not to:
        return False, "Invalid phone for WhatsApp."

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    body = f"From={_enc(from_)}&To={_enc(to)}&Body={_enc(message[:1600])}"
    req = Request(
        url,
        data=body.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
    )
    import base64

    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {auth}")

    try:
        with urlopen(req, timeout=30) as resp:
            if resp.status >= 400:
                return False, f"Twilio HTTP {resp.status}"
    except HTTPError as e:
        return False, f"Twilio HTTP {e.code}"
    except URLError as e:
        return False, str(e.reason or e)
    return True, None


def send_email_with_retry(
    to_addr: str,
    subject: str,
    body_text: str,
    *,
    body_html: str | None = None,
    retries: int = 2,
    message_kind: str | None = None,
    context: dict | None = None,
) -> tuple[bool, str | None]:
    attempts = max(1, int(retries) + 1)
    last_err = None
    for _ in range(attempts):
        ok, err = send_email(to_addr, subject, body_text, body_html=body_html)
        if ok:
            _log_delivery(
                channel="email",
                recipient=to_addr,
                subject=subject,
                message_kind=message_kind,
                success=True,
                attempt_count=attempts,
                error=None,
                context=context,
            )
            return True, None
        last_err = err
    _log_delivery(
        channel="email",
        recipient=to_addr,
        subject=subject,
        message_kind=message_kind,
        success=False,
        attempt_count=attempts,
        error=last_err,
        context=context,
    )
    return False, last_err


def send_whatsapp_with_retry(
    to_phone_normalized: str,
    message: str,
    *,
    retries: int = 1,
    message_kind: str | None = None,
    context: dict | None = None,
) -> tuple[bool, str | None]:
    attempts = max(1, int(retries) + 1)
    last_err = None
    for _ in range(attempts):
        ok, err = send_whatsapp_text(to_phone_normalized, message)
        if ok:
            _log_delivery(
                channel="whatsapp",
                recipient=to_phone_normalized,
                subject=None,
                message_kind=message_kind,
                success=True,
                attempt_count=attempts,
                error=None,
                context=context,
            )
            return True, None
        last_err = err
    _log_delivery(
        channel="whatsapp",
        recipient=to_phone_normalized,
        subject=None,
        message_kind=message_kind,
        success=False,
        attempt_count=attempts,
        error=last_err,
        context=context,
    )
    return False, last_err


def _enc(s: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(s, safe="")


def _whatsapp_for_member_messages() -> bool:
    ex = _extra()
    if ex.get("notify_members_whatsapp"):
        return True
    return _truthy_env("ESTITHMAR_NOTIFY_WHATSAPP")


def notify_member_channel(
    *,
    email_to: str | None,
    phone: str | None,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    send_whatsapp_too: bool = True,
) -> None:
    """Send email and optionally WhatsApp to a member (respects settings)."""
    app = current_app
    if email_to and mail_configured():
        ok, err = send_email_with_retry(
            email_to.strip(),
            subject,
            body_text,
            body_html=body_html,
            retries=2,
            message_kind="member_event",
            context={"subject": subject},
        )
        if not ok and app:
            app.logger.warning("Member notification email failed: %s", err)
    if send_whatsapp_too and phone and whatsapp_configured() and _whatsapp_for_member_messages():
        short = body_text.replace("\n", " ")[:1500]
        ok, err = send_whatsapp_with_retry(
            phone,
            short,
            retries=1,
            message_kind="member_event",
            context={"subject": subject},
        )
        if not ok and app:
            app.logger.warning("Member notification WhatsApp failed: %s", err)


def run_due_report_schedules(now: datetime | None = None) -> dict[str, int]:
    """Run active report schedules that are due and email a compact digest."""
    run_at = now or datetime.utcnow()
    due = (
        ReportSchedule.query.filter(
            ReportSchedule.is_active.is_(True),
            ReportSchedule.next_run_at.isnot(None),
            ReportSchedule.next_run_at <= run_at,
        )
        .order_by(ReportSchedule.next_run_at.asc())
        .all()
    )
    sent = 0
    failed = 0
    for row in due:
        recipients = [x.strip() for x in (row.recipients or "").split(",") if x.strip()]
        if not recipients:
            row.last_status = "failed"
            row.last_error = "No recipients configured."
            row.last_run_at = run_at
            row.next_run_at = run_at + timedelta(days=1)
            db.session.commit()
            failed += 1
            continue
        subject = f"Estithmar scheduled report — {row.name}"
        body = (
            f"Scheduled report: {row.name}\n"
            f"Report key: {row.report_key}\n"
            f"Run time (UTC): {run_at}\n"
            "Open Reports hub in Estithmar to review current dashboard values."
        )
        report_html = try_render_transactional(
            audience="Team",
            title=f"Scheduled report: {row.name}",
            intro=(
                f"Your saved schedule ran at {run_at} (UTC).\n\n"
                "Open the reporting area in Estithmar to view the current figures for this report key."
            ),
            detail_rows=[
                ("Report key", str(row.report_key)),
                ("Run time (UTC)", str(run_at)),
            ],
            cta_url=None,
            cta_label=None,
        )
        ok_all = True
        err_msg = None
        for rcpt in recipients:
            ok, err = send_email_with_retry(
                rcpt,
                subject,
                body,
                body_html=report_html,
                retries=2,
                message_kind="report_schedule",
                context={"schedule_id": row.id, "report_key": row.report_key},
            )
            if not ok:
                ok_all = False
                err_msg = err
        row.last_run_at = run_at
        row.last_status = "sent" if ok_all else "failed"
        row.last_error = (err_msg or "")[:500] if err_msg else None
        if row.frequency == "daily":
            row.next_run_at = run_at + timedelta(days=1)
        elif row.frequency == "monthly":
            row.next_run_at = run_at + timedelta(days=30)
        else:
            row.next_run_at = run_at + timedelta(days=7)
        db.session.commit()
        if ok_all:
            sent += 1
        else:
            failed += 1
    return {"due": len(due), "sent": sent, "failed": failed}


def notify_member_welcome(
    *,
    member_name: str,
    member_code: str,
    email: str | None,
    phone: str | None,
    extra: str = "",
) -> None:
    """Send welcome email/WhatsApp for a new member (respects Settings → member notifications)."""
    ex = _extra()
    if not ex.get("notify_members_enabled", True):
        return
    if not ex.get("notify_member_welcome", True):
        return
    if not email and not phone:
        return
    app = current_app
    lines = [
        f"Hello {member_name},",
        "",
        f"Your member record is registered in Estithmar ({member_code}).",
        extra.strip(),
        "",
        "You can sign in to the portal if you have an account.",
    ]
    text = "\n".join(lines)
    li = login_url() or None
    welcome_html = try_render_transactional(
        audience="Member",
        title="Welcome",
        intro=text,
        cta_url=li,
        cta_label="Sign in to the portal" if li else None,
    )
    if email and mail_configured():
        ok, err = send_email_with_retry(
            email.strip(),
            "Estithmar — registration",
            text,
            body_html=welcome_html,
            retries=2,
            message_kind="member_welcome",
            context={"member_code": member_code},
        )
        if not ok and app:
            app.logger.warning("Welcome email failed: %s", err)
    if phone and whatsapp_configured() and _whatsapp_for_member_messages():
        short = text.replace("\n", " ")[:1500]
        ok, err = send_whatsapp_with_retry(
            phone,
            short,
            retries=1,
            message_kind="member_welcome",
            context={"member_code": member_code},
        )
        if not ok and app:
            app.logger.warning("Welcome WhatsApp failed: %s", err)


def notify_user_credentials(
    *,
    to_email: str,
    username: str,
    role_label: str,
    password_plain: str | None = None,
    message: str = "",
) -> None:
    if not to_email:
        return
    if not mail_configured():
        if current_app:
            current_app.logger.info("Skipping credential email (mail not configured).")
        return
    body = [
        "Hello,",
        "",
        f"An Estithmar account was created for you ({role_label}).",
        f"Username: {username}",
    ]
    if password_plain:
        body.append(f"Password: {password_plain}")
    body.append("")
    body.append("Sign in at your Estithmar web address.")
    if message:
        body.append("")
        body.append(message)
    text = "\n".join(body)
    rows = [("Role", str(role_label)), ("Username", str(username))]
    if password_plain:
        rows.append(("Password", str(password_plain)))
    li = login_url() or None
    intro = (
        "An Estithmar portal account was created for you. "
        "Use the credentials below to sign in, then change your password from your profile for security."
    )
    if message:
        intro = intro + f"\n\n{message}"
    cred_html = try_render_transactional(
        audience=audience_for_role_label(role_label),
        title="Your account is ready",
        intro=intro,
        detail_rows=rows,
        cta_url=li,
        cta_label="Sign in" if li else None,
        secondary_note="For security, change your password after the first sign-in if your administrator asked you to.",
    )
    ok, err = send_email_with_retry(
        to_email,
        "Estithmar — your account",
        text,
        body_html=cred_html,
        retries=2,
        message_kind="user_credentials",
        context={"role": role_label},
    )
    if not ok and current_app:
        current_app.logger.warning("User notify email failed: %s", err)


def notify_password_reset(*, to_email: str, temp_password: str) -> None:
    if not to_email or not mail_configured():
        return
    text = (
        "Your Estithmar password was reset.\n\n"
        f"Temporary password: {temp_password}\n\n"
        "Sign in and change your password in Profile."
    )
    li = login_url() or None
    reset_html = try_render_transactional(
        audience="Account",
        title="Password reset",
        intro="Your sign-in password was reset by a password recovery request. Use the temporary password below, then set a new password in your profile right away.",
        detail_rows=[("Temporary password", str(temp_password))],
        cta_url=li,
        cta_label="Sign in" if li else None,
        secondary_note="If you did not request this, contact your administrator immediately.",
    )
    ok, err = send_email_with_retry(
        to_email,
        "Estithmar — password reset",
        text,
        body_html=reset_html,
        retries=2,
        message_kind="password_reset",
        context={},
    )
    if not ok and current_app:
        current_app.logger.warning("Password reset email failed: %s", err)
