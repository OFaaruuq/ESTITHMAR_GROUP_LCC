"""Email (SMTP) and WhatsApp (Twilio) — environment and/or Settings → Notifications."""

from __future__ import annotations

import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app, has_request_context

from istithmar.models import get_or_create_settings


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
        tls_raw = os.environ.get("ISTITHMAR_MAIL_USE_TLS", "true")
    use_tls = str(tls_raw).strip().lower() not in ("0", "false", "no")
    port_raw = ex.get("smtp_port") or os.environ.get("ISTITHMAR_MAIL_PORT") or "587"
    try:
        port_int = int(port_raw)
    except (TypeError, ValueError):
        port_int = 587
    return {
        "host": (ex.get("smtp_host") or os.environ.get("ISTITHMAR_MAIL_SERVER") or "").strip(),
        "port": port_int,
        "use_tls": use_tls,
        "username": (ex.get("smtp_username") or os.environ.get("ISTITHMAR_MAIL_USERNAME") or "").strip(),
        "password": (
            ex.get("smtp_password")
            if ex.get("smtp_password") is not None
            else os.environ.get("ISTITHMAR_MAIL_PASSWORD")
        ),
        "sender": (ex.get("smtp_sender") or os.environ.get("ISTITHMAR_MAIL_SENDER") or "").strip(),
    }


def effective_twilio() -> dict[str, str]:
    ex = _extra()
    return {
        "sid": (ex.get("twilio_account_sid") or os.environ.get("TWILIO_ACCOUNT_SID") or "").strip(),
        "token": (ex.get("twilio_auth_token") or os.environ.get("TWILIO_AUTH_TOKEN") or "").strip(),
        "from": (ex.get("twilio_whatsapp_from") or os.environ.get("TWILIO_WHATSAPP_FROM") or "").strip(),
        "default_cc": (
            ex.get("whatsapp_default_cc") or os.environ.get("ISTITHMAR_WHATSAPP_DEFAULT_CC") or ""
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


def _enc(s: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(s, safe="")


def _whatsapp_for_member_messages() -> bool:
    ex = _extra()
    if ex.get("notify_members_whatsapp"):
        return True
    return _truthy_env("ISTITHMAR_NOTIFY_WHATSAPP")


def notify_member_channel(
    *,
    email_to: str | None,
    phone: str | None,
    subject: str,
    body_text: str,
    send_whatsapp_too: bool = True,
) -> None:
    """Send email and optionally WhatsApp to a member (respects settings)."""
    app = current_app
    if email_to and mail_configured():
        ok, err = send_email(email_to.strip(), subject, body_text)
        if not ok and app:
            app.logger.warning("Member notification email failed: %s", err)
    if send_whatsapp_too and phone and whatsapp_configured() and _whatsapp_for_member_messages():
        short = body_text.replace("\n", " ")[:1500]
        ok, err = send_whatsapp_text(phone, short)
        if not ok and app:
            app.logger.warning("Member notification WhatsApp failed: %s", err)


def notify_member_welcome(
    *,
    member_name: str,
    member_code: str,
    email: str | None,
    phone: str | None,
    extra: str = "",
) -> None:
    if not email and not phone:
        return
    app = current_app
    lines = [
        f"Hello {member_name},",
        "",
        f"Your member record is registered in Istithmar ({member_code}).",
        extra.strip(),
        "",
        "You can sign in to the portal if you have an account.",
    ]
    text = "\n".join(lines)
    if email and mail_configured():
        ok, err = send_email(email.strip(), "Istithmar — registration", text)
        if not ok and app:
            app.logger.warning("Welcome email failed: %s", err)
    if phone and whatsapp_configured() and _whatsapp_for_member_messages():
        ok, err = send_whatsapp_text(phone, text.replace("\n", " ")[:1500])
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
        f"An Istithmar account was created for you ({role_label}).",
        f"Username: {username}",
    ]
    if password_plain:
        body.append(f"Password: {password_plain}")
    body.append("")
    body.append("Sign in at your Istithmar web address.")
    if message:
        body.append("")
        body.append(message)
    text = "\n".join(body)
    ok, err = send_email(to_email, "Istithmar — your account", text)
    if not ok and current_app:
        current_app.logger.warning("User notify email failed: %s", err)


def notify_password_reset(*, to_email: str, temp_password: str) -> None:
    if not to_email or not mail_configured():
        return
    text = (
        "Your Istithmar password was reset.\n\n"
        f"Temporary password: {temp_password}\n\n"
        "Sign in and change your password in Profile."
    )
    ok, err = send_email(to_email, "Istithmar — password reset", text)
    if not ok and current_app:
        current_app.logger.warning("Password reset email failed: %s", err)
