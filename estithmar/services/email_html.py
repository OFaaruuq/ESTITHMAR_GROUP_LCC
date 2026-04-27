"""Render HTML bodies for transactional emails (member, agent, staff) — use with plain-text fallback."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from flask import current_app, has_request_context, render_template, request, url_for

from estithmar.models import get_or_create_settings

# HTML reference must match the Content-ID set in :func:`estithmar.services.notifications.send_email`
ESTITHMAR_EMAIL_LOGO_CID = "estithmar-logo"


def _is_loopback_url(url: str) -> bool:
    """Gmail fetches <img> URLs from its servers — localhost/127.0.0.1 are never reachable."""
    if not (url and isinstance(url, str) and "://" in url):
        return False
    try:
        h = (urlparse(url.strip()).hostname or "").lower()
    except Exception:
        return True
    return h in (
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "[::1]",
    )


def _safe_brand_relpath(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().replace("\\", "/")
    if not s or ".." in s or "://" in s or s.startswith("/"):
        return None
    return s


def brand_logo_local_path() -> str | None:
    """
    Absolute path to the light branding logo file on disk, if it exists and is under the static folder.
    Used to embed the image via Content-ID (works in Gmail; URL-based /static/... on localhost does not).
    """
    if not has_request_context():
        return None
    try:
        ex0 = get_or_create_settings().get_extra()
        relp = _safe_brand_relpath(ex0.get("logo_light") if ex0 else None)
        if not relp:
            return None
        base = os.path.normpath(current_app.static_folder or "")
        if not base or not os.path.isdir(base):
            return None
        abspath = os.path.normpath(os.path.join(base, relp))
        if not abspath.startswith(base + os.sep) and abspath != base:
            return None
        return abspath if os.path.isfile(abspath) else None
    except Exception:
        return None


def _public_base_from_settings() -> str:
    if not has_request_context():
        return ""
    try:
        ex = get_or_create_settings().get_extra()
        return (ex.get("public_site_url") or os.environ.get("ESTITHMAR_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    except Exception:
        return os.environ.get("ESTITHMAR_PUBLIC_SITE_URL", "").strip().rstrip("/")


def brand_for_email() -> dict[str, str | None]:
    """
    org_name, org_subtitle, footer_address, and logo_src for the template.

    logo_src may be a full https URL, or ``cid:estithmar-logo`` (inline attachment added in :func:`send_email`).
    """
    org = "Estithmar"
    sub = "Community investment"
    address: str | None = None
    logo_src: str | None = None
    if not has_request_context():
        return {
            "org_name": org,
            "org_subtitle": sub,
            "footer_address": address,
            "logo_src": None,
        }
    try:
        ex = get_or_create_settings().get_extra()
        org = (ex.get("app_display_name") or ex.get("company_name") or "Estithmar").strip() or "Estithmar"
        tag = (ex.get("app_footer_tagline") or "").strip()[:240]
        sub = tag or "Member & partner communications"
        address = (ex.get("company_address") or "").strip()[:500] or None
        if address == "":
            address = None
        raw = (ex.get("logo_light") or "").strip()
        relp = _safe_brand_relpath(raw)
        logo_src = None  # set by branches below
        # 1) Full public URL in settings
        if raw and re.match(r"^https?://", raw, re.IGNORECASE):
            logo_src = raw if not _is_loopback_url(raw) else None
        # 2) File on this server: embed (best for external mail clients)
        elif brand_logo_local_path():
            logo_src = f"cid:{ESTITHMAR_EMAIL_LOGO_CID}"
        # 3) Public site base (production) + relative static path — optional setting / env
        elif relp:
            pub = _public_base_from_settings()
            if pub:
                join = f"{pub.rstrip('/')}/{relp.lstrip('/')}"
                if not _is_loopback_url(join):
                    logo_src = join
            if not logo_src:
                # 4) Same deployment URL (skip in email if loopback / unreachable to Gmail)
                try:
                    candidate = url_for("static", filename=relp, _external=True)
                except Exception:
                    candidate = None
                if candidate and not _is_loopback_url(candidate):
                    logo_src = candidate
    except Exception:
        pass
    return {
        "org_name": org,
        "org_subtitle": sub,
        "footer_address": address,
        "logo_src": logo_src,
    }


def audience_for_role_label(role_label: str) -> str:
    r = (role_label or "").lower()
    if "agent" in r:
        return "Agent"
    if "member" in r:
        return "Member"
    if "operator" in r or "admin" in r or "finance" in r:
        return "Team"
    return "Team"


def login_url() -> str:
    if not has_request_context():
        return ""
    try:
        return url_for("login", _external=True)
    except Exception:
        try:
            return request.url_root.rstrip("/") + "/login"
        except Exception:
            return ""


def try_render_transactional(**kwargs) -> str | None:
    try:
        return render_transactional_email(**kwargs)
    except Exception:
        return None


def public_portal_url() -> str | None:
    """Base URL of this deployment (for email links when not passing a path)."""
    if not has_request_context():
        return None
    try:
        return request.url_root.rstrip("/")
    except Exception:
        return None


def render_transactional_email(
    *,
    audience: str,
    title: str,
    intro: str,
    detail_rows: list[tuple[str, str]] | None = None,
    cta_url: str | None = None,
    cta_label: str | None = None,
    secondary_note: str = "",
) -> str:
    """
    audience: short label shown in header (e.g. Member, Agent, Team).
    intro: main paragraph; line breaks preserved.
    detail_rows: (label, value) pairs in a clean table.
    """
    b = brand_for_email()
    cta_lbl = None
    if cta_url:
        cta_lbl = cta_label if cta_label is not None and str(cta_label).strip() else "Open in Estithmar"
    return render_template(
        "emails/transactional.html",
        audience=audience,
        title=title,
        intro=intro,
        detail_rows=detail_rows or [],
        cta_url=cta_url,
        cta_label=cta_lbl,
        secondary_note=secondary_note,
        org_name=b["org_name"],
        org_subtitle=b["org_subtitle"] or "",
        footer_address=b["footer_address"] or "",
        logo_src=b["logo_src"],
    )
