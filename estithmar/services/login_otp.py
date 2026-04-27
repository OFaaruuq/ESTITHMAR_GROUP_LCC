"""Email one-time passcode (OTP) for password login — all AppUser accounts."""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from estithmar import db
from estithmar.models import AppUser, get_or_create_settings, LoginOtpChallenge
from estithmar.services.email_html import try_render_transactional
from estithmar.services.notifications import mail_configured, send_email_with_retry

SESSION_NONCE_KEY = "lotp_nonce"
OTP_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 6


def is_otp_required() -> bool:
    if (os.environ.get("ESTITHMAR_DISABLE_LOGIN_OTP") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    ex: dict[str, Any] = get_or_create_settings().get_extra() or {}
    return ex.get("require_login_otp", True) is not False


def has_pending_verification() -> bool:
    return bool(session.get(SESSION_NONCE_KEY))


def _invalidate_user_pending_challenges(user_id: int) -> None:
    now = datetime.utcnow()
    q = (
        db.session.query(LoginOtpChallenge)
        .filter(LoginOtpChallenge.user_id == int(user_id), LoginOtpChallenge.consumed_at.is_(None))
        .all()
    )
    for row in q:
        row.consumed_at = now
    if q:
        db.session.commit()


def _send_login_otp_email(to: str, full_name: str, code: str) -> bool:
    org = (get_or_create_settings().get_extra() or {}).get("app_display_name")
    if not (org and str(org).strip()):
        org = (get_or_create_settings().get_extra() or {}).get("company_name") or "Estithmar"
    org = str(org).strip() or "Estithmar"
    subject = f"{org} — sign-in code: {code}"
    lead = f"Your one-time sign-in code is: {code}.\n\n"
    lead += "It expires in 10 minutes. If you did not try to sign in, change your password and contact support."
    plain = f"Hello{(' ' + full_name) if full_name else ''},\n\n" + lead + f"\n— {org}\n"
    intro = f"Hello{(' ' + full_name) if full_name else ''},\n\n" + f"Your one-time sign-in code is: {code}. It expires in 10 minutes.\n\n"
    intro += "If you did not try to sign in, change your password and contact your administrator."
    detail_rows: list[tuple[str, str]] = [
        ("Code", code),
        ("Valid for", "10 minutes"),
    ]
    body_html = try_render_transactional(
        audience="Team",
        title="Sign-in verification",
        intro=intro,
        detail_rows=detail_rows,
    )
    ok, _ = send_email_with_retry(
        to,
        subject,
        plain,
        body_html=body_html,
        retries=2,
        message_kind="login_otp",
        context={"to": to[:4] + "…" if len(to) > 6 else to},
    )
    return bool(ok)


def start_challenge_for_user(
    user: AppUser,
    next_path: str,
    *,
    client_ip: str | None,
) -> tuple[bool, str | None]:
    """
    Create OTP, email it, set session key. Return (ok, err).
    err: 'no_email' | 'no_smtp' | 'send_failed'
    """
    if not is_otp_required():
        return False, "not_required"
    to = (user.email or "").strip()
    if not to or "@" not in to:
        return False, "no_email"
    if not mail_configured():
        return False, "no_smtp"

    _invalidate_user_pending_challenges(user.id)
    code = f"{secrets.randbelow(1_000_000):06d}"
    ch = LoginOtpChallenge(
        user_id=user.id,
        nonce=secrets.token_urlsafe(32)[:64],
        code_hash=generate_password_hash(code),
        expires_at=datetime.utcnow() + OTP_TTL,
        client_ip=(client_ip or "")[:64] or None,
        next_path=(next_path or "")[:300] or None,
        attempt_count=0,
    )
    db.session.add(ch)
    db.session.commit()

    if not _send_login_otp_email(to, (user.full_name or "").strip() or (user.username or "user"), code):
        db.session.delete(ch)
        db.session.commit()
        return False, "send_failed"
    session[SESSION_NONCE_KEY] = ch.nonce
    return True, None


def verify_submitted_code(raw: str) -> tuple[AppUser | None, str, str | None]:
    """
    Check 6-digit code, consume challenge, clear session.
    Returns (user, next_path, None) on success, or (None, '', err).
    err: 'session' | 'not_found' | 'expired' | 'locked' | 'invalid' | 'user'
    """
    nonce = session.get(SESSION_NONCE_KEY)
    if not nonce:
        return None, "", "session"
    ch = LoginOtpChallenge.query.filter_by(nonce=nonce, consumed_at=None).first()
    if not ch:
        session.pop(SESSION_NONCE_KEY, None)
        return None, "", "not_found"
    nxt = (ch.next_path or "").strip()
    if not nxt.startswith("/"):
        nxt = ""
    now = datetime.utcnow()
    if ch.expires_at < now:
        ch.consumed_at = now
        db.session.commit()
        session.pop(SESSION_NONCE_KEY, None)
        return None, "", "expired"
    if (ch.attempt_count or 0) >= MAX_CODE_ATTEMPTS:
        ch.consumed_at = now
        db.session.commit()
        session.pop(SESSION_NONCE_KEY, None)
        return None, "", "locked"
    s = re.sub(r"\D", "", (raw or "")[:20])
    if len(s) != 6 or not s.isdigit():
        ch.attempt_count = (ch.attempt_count or 0) + 1
        db.session.commit()
        return None, nxt, "invalid"
    if not check_password_hash(ch.code_hash, s):
        ch.attempt_count = (ch.attempt_count or 0) + 1
        db.session.commit()
        return None, nxt, "invalid"
    ch.consumed_at = now
    u = db.session.get(AppUser, ch.user_id)
    db.session.commit()
    session.pop(SESSION_NONCE_KEY, None)
    if u is None or not u.is_active:
        return None, nxt, "user"
    return u, nxt, None


def can_resend_now() -> bool:
    if session.get("_lotp_resend_cooldown_ts"):
        from time import time

        if time() < float(session.get("_lotp_resend_cooldown_ts", 0)):
            return False
    return True


def mark_resend_cooldown(seconds: int = 45) -> None:
    from time import time

    session["_lotp_resend_cooldown_ts"] = time() + seconds


def resend_from_session(user_loader_ip: str | None) -> tuple[bool, str | None]:
    """Re-issue OTP for the pending challenge's user. err same as start_challenge."""
    nonce = session.get(SESSION_NONCE_KEY)
    if not nonce:
        return False, "session"
    ch = LoginOtpChallenge.query.filter_by(nonce=nonce, consumed_at=None).first()
    if not ch or ch.expires_at < datetime.utcnow():
        return False, "expired"
    u = db.session.get(AppUser, ch.user_id)
    if not u:
        return False, "user"
    nxt = (ch.next_path or "")[:300] or ""
    return start_challenge_for_user(
        u,
        nxt if nxt.startswith("/") else "",
        client_ip=user_loader_ip,
    )


def clear_session() -> None:
    session.pop(SESSION_NONCE_KEY, None)
    session.pop("_lotp_resend_cooldown_ts", None)
