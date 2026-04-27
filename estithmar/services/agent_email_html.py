"""HTML body for agent portfolio & KPI emails (rich layout)."""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal
from typing import Any

from flask import render_template

from estithmar.models import Agent
from estithmar.services.email_html import brand_for_email

logger = logging.getLogger(__name__)


def _f(sym: str, cur: str, d: Any) -> str:
    a = d if isinstance(d, Decimal) else Decimal(str(d or 0))
    return f"{sym}{a:,.2f} {cur}"


def build_agent_portfolio_template_context(
    k: dict,
    agent: Agent,
    *,
    title: str,
    intro: str,
    cta_url: str | None,
    cta_label: str | None,
    payment_alert: dict | None = None,
) -> dict:
    """
    Build template variables for ``emails/agent_portfolio.html``.
    ``k`` is the return value of :func:`estithmar.services.agent_kpi.compute_agent_kpis`.
    """
    b = brand_for_email()
    sc: Counter = k.get("status_counter") or Counter()
    sym = k.get("currency_symbol") or "$"
    cur = k.get("currency_code") or "USD"
    p = int(sc.get("Pending", 0) or 0)
    pa = int(sc.get("Partially Paid", 0) or 0)
    n_fully = int(sc.get("Fully Paid", 0) or 0)
    c = int(sc.get("Cancelled", 0) or 0)
    active = p + pa + n_fully
    if active > 0:
        w1 = max(0, min(100, int(round(100.0 * p / active))))
        w2 = max(0, min(100, int(round(100.0 * pa / active))))
        w3 = max(0, 100 - w1 - w2)
    else:
        w1 = w2 = w3 = 0

    cta_lbl = None
    if cta_url:
        cta_lbl = cta_label if cta_label and str(cta_label).strip() else "Open dashboard"

    return {
        "org_name": b["org_name"],
        "org_subtitle": b.get("org_subtitle") or "",
        "footer_address": b.get("footer_address") or "",
        "logo_src": b.get("logo_src"),
        "title": title,
        "intro": intro,
        "agent_name": agent.full_name,
        "agent_code": agent.agent_id,
        "subscribed": _f(sym, cur, k.get("total_subscribed", 0)),
        "collected": _f(sym, cur, k.get("total_collected", 0)),
        "outstanding": _f(sym, cur, k.get("total_outstanding", 0)),
        "fully_paid_value": _f(sym, cur, k.get("fully_paid_value", 0)),
        "install_open": _f(sym, cur, k.get("installment_due_balance", 0)),
        "members_active": int(k.get("members_active", 0) or 0),
        "members_total": int(k.get("members_total", 0) or 0),
        "receipts_count": int(k.get("receipts_count", 0) or 0),
        "sc_pending": p,
        "sc_partial": pa,
        "sc_fully": n_fully,
        "sc_cancelled": c,
        "bar_w1": w1,
        "bar_w2": w2,
        "bar_w3": w3,
        "bar_has_data": active > 0,
        "confirmed": int(k.get("confirmed_subscriptions", 0) or 0),
        "install_overdue": int(k.get("installment_overdue_count", 0) or 0),
        "certs_issued": int(k.get("certificates_issued", 0) or 0),
        "certs_pending": int(k.get("pending_certificates", 0) or 0),
        "cta_url": cta_url,
        "cta_label": cta_lbl,
        "payment_alert": payment_alert,
    }


def render_agent_portfolio_html(
    k: dict,
    agent: Agent,
    *,
    title: str,
    intro: str,
    cta_url: str | None,
    cta_label: str | None = None,
    payment_alert: dict | None = None,
) -> str:
    """Render the agent portfolio / KPI email HTML document."""
    ctx = build_agent_portfolio_template_context(
        k,
        agent,
        title=title,
        intro=intro,
        cta_url=cta_url,
        cta_label=cta_label,
        payment_alert=payment_alert,
    )
    return render_template("emails/agent_portfolio.html", **ctx)


def try_render_agent_portfolio_html(
    k: dict,
    agent: Agent,
    *,
    title: str,
    intro: str,
    cta_url: str | None,
    cta_label: str | None = None,
    payment_alert: dict | None = None,
) -> str | None:
    try:
        return render_agent_portfolio_html(
            k,
            agent,
            title=title,
            intro=intro,
            cta_url=cta_url,
            cta_label=cta_label,
            payment_alert=payment_alert,
        )
    except Exception:
        logger.exception("Failed to render agent_portfolio.html (agent_id=%s)", agent.id)
        return None
