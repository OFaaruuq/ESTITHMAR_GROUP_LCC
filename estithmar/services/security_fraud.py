"""Basic fraud heuristics, login-attempt log, and security alert rows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func

from estithmar import db
from estithmar.models import LoginAttempt, SecurityAlert, UserSessionLog


def _now() -> datetime:
    return datetime.utcnow()


def _hint_username(raw: str | None) -> str:
    s = (raw or "").strip()
    if len(s) <= 2:
        return "***"
    return s[0] + "*" * (min(len(s), 5) - 1) + s[-1] if len(s) > 2 else s


def record_login_attempt(
    *,
    ip: str,
    ident: str | None,
    success: bool,
    user_id: int | None = None,
    device_fp: str | None = None,
) -> None:
    row = LoginAttempt(
        ip_address=(ip or "")[:64],
        username_hint=_hint_username(ident),
        success=success,
        app_user_id=user_id,
        device_fingerprint=(device_fp or "")[:64] or None,
    )
    db.session.add(row)


def count_recent_failed_logins_for_ip(ip: str, minutes: int = 15) -> int:
    if not ip:
        return 0
    since = _now() - timedelta(minutes=minutes)
    n = (
        db.session.query(func.count(LoginAttempt.id))
        .filter(
            LoginAttempt.ip_address == (ip or "")[:64],
            LoginAttempt.success == False,  # noqa: E712
            LoginAttempt.created_at >= since,
        )
        .scalar()
    )
    return int(n or 0)


def has_seen_device_fingerprint_for_user(
    user_id: int, fingerprint: str, lookback_days: int = 365, exclude_session_id: int | None = None
) -> bool:
    if not fingerprint or not user_id:
        return True
    since = _now() - timedelta(days=lookback_days)
    qy = (
        db.session.query(UserSessionLog.id)
        .filter(
            UserSessionLog.user_id == user_id,
            UserSessionLog.device_fingerprint == fingerprint,
            UserSessionLog.login_at >= since,
        )
    )
    if exclude_session_id is not None:
        qy = qy.filter(UserSessionLog.id != int(exclude_session_id))
    return bool(qy.first())


def _recent_duplicate_alert(
    user_id: int | None, rule: str, window_mins: int = 60
) -> bool:
    since = _now() - timedelta(minutes=window_mins)
    q = (
        db.session.query(SecurityAlert.id)
        .filter(
            SecurityAlert.rule_code == rule,
            SecurityAlert.created_at >= since,
        )
    )
    if user_id is not None:
        q = q.filter(SecurityAlert.app_user_id == user_id)
    return bool(q.first())


def evaluate_post_login_security(
    user_id: int, session_row: UserSessionLog
) -> None:
    """
    Heuristics after a successful session row is created:
    - New device: fingerprint not seen in lookback for this user.
    """
    fp = (getattr(session_row, "device_fingerprint", None) or "").strip()
    if not fp or not user_id:
        return
    if has_seen_device_fingerprint_for_user(
        user_id, fp, lookback_days=365, exclude_session_id=int(session_row.id)
    ) or _recent_duplicate_alert(user_id, "new_device", 120):
        return
    n_prev = (
        db.session.query(func.count(UserSessionLog.id))
        .filter(
            UserSessionLog.user_id == user_id,
            UserSessionLog.id != session_row.id,
        )
        .scalar()
    )
    if int(n_prev or 0) < 1:
        return
    a = SecurityAlert(
        app_user_id=user_id,
        rule_code="new_device",
        severity="info",
        message="Sign-in from a new device profile (fingerprint not seen in the last year).",
        context_json=json.dumps({"fingerprint": fp[:16] + "…", "session_id": session_row.id}),
        ip_address=(getattr(session_row, "ip_address", None) or "")[:64] or None,
    )
    db.session.add(a)


def check_multi_ip_for_user(user_id: int) -> None:
    """If user has many distinct IPs in 24h, raise one alert (call after successful login)."""
    if not user_id:
        return
    since = _now() - timedelta(hours=24)
    r = (
        db.session.query(func.count(func.distinct(UserSessionLog.ip_address)))
        .filter(
            UserSessionLog.user_id == user_id,
            UserSessionLog.login_at >= since,
            UserSessionLog.ip_address.isnot(None),
            UserSessionLog.ip_address != "",
        )
        .scalar()
    )
    n = int(r or 0)
    if n >= 3:
        alert_multi_ip_user(user_id, n)


def alert_multi_ip_user(user_id: int, ip_count: int) -> None:
    if not user_id or int(ip_count or 0) < 3:
        return
    if _recent_duplicate_alert(user_id, "multi_ip_24h", 24 * 60):
        return
    a = SecurityAlert(
        app_user_id=user_id,
        rule_code="multi_ip_24h",
        severity="warning",
        message=f"User had {int(ip_count)} distinct IPs in 24h (session history).",
        context_json=None,
    )
    db.session.add(a)


def alert_bruteforce_suspect(ip: str) -> None:
    if not (ip or "").strip():
        return
    if _recent_bruteforce_alert_for_ip((ip or "")[:64], minutes=30):
        return
    a = SecurityAlert(
        app_user_id=None,
        rule_code="bruteforce_suspect",
        severity="high",
        message="Multiple failed sign-in attempts from this IP in a short window.",
        context_json=json.dumps({"ip": (ip or "")[:64]}),
        ip_address=(ip or "")[:64],
    )
    db.session.add(a)


def _recent_bruteforce_alert_for_ip(ip: str, minutes: int) -> bool:
    since = _now() - timedelta(minutes=minutes)
    ex = (
        db.session.query(SecurityAlert.id)
        .filter(
            SecurityAlert.rule_code == "bruteforce_suspect",
            SecurityAlert.ip_address == (ip or "")[:64],
            SecurityAlert.created_at >= since,
        )
        .first()
    )
    return bool(ex)
