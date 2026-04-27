"""Email agents with portfolio KPIs and payment activity."""

from __future__ import annotations

from decimal import Decimal

from flask import current_app, url_for

from estithmar import db
from estithmar.models import Agent, Contribution, Member, get_or_create_settings
from estithmar.services.agent_kpi import compute_agent_kpis
from estithmar.services.email_html import try_render_transactional
from estithmar.services.notifications import mail_configured, send_email_with_retry


def _ex() -> dict:
    return get_or_create_settings().get_extra()


def should_notify_agents() -> bool:
    return bool(_ex().get("notify_agents_enabled", True))


def should_notify_agent_on_payment() -> bool:
    if not should_notify_agents():
        return False
    return bool(_ex().get("notify_agent_kpi_on_payment", True))


def _fmt(sym: str, cur: str, d: Decimal) -> str:
    a = d or Decimal("0")
    return f"{sym}{a:,.2f} {cur}"


def _kpi_rows(k: dict) -> list[tuple[str, str]]:
    if not k:
        return [("Status", "No data")]
    sc = k.get("status_counter")
    if sc is None:
        from collections import Counter

        sc = Counter()
    return [
        ("Active members", str(k.get("members_active", 0))),
        ("Total members (assigned)", str(k.get("members_total", 0))),
        ("Payments recorded (receipts)", str(k.get("receipts_count", 0))),
        (
            "Total collected (net)",
            _fmt(
                k["currency_symbol"],
                k["currency_code"],
                k.get("total_collected", Decimal("0")),
            ),
        ),
        (
            "Total subscribed (excl. cancelled)",
            _fmt(
                k["currency_symbol"],
                k["currency_code"],
                k.get("total_subscribed", Decimal("0")),
            ),
        ),
        (
            "Outstanding balance (subscriptions)",
            _fmt(
                k["currency_symbol"],
                k["currency_code"],
                k.get("total_outstanding", Decimal("0")),
            ),
        ),
        (
            "Fully paid — subscribed value",
            _fmt(
                k["currency_symbol"],
                k["currency_code"],
                k.get("fully_paid_value", Decimal("0")),
            ),
        ),
        ("Subscriptions — Pending", str(sc.get("Pending", 0))),
        ("Subscriptions — Partially paid", str(sc.get("Partially Paid", 0))),
        ("Subscriptions — Fully paid", str(sc.get("Fully Paid", 0))),
        ("Subscriptions — Cancelled", str(sc.get("Cancelled", 0))),
        (
            "Confirmed (fully paid + confirmed)",
            str(k.get("confirmed_subscriptions", 0)),
        ),
        (
            "Installments — overdue (count)",
            str(k.get("installment_overdue_count", 0)),
        ),
        (
            "Installments — open balance",
            _fmt(
                k["currency_symbol"],
                k["currency_code"],
                k.get("installment_due_balance", Decimal("0")),
            ),
        ),
        (
            "Certificates — issued",
            str(k.get("certificates_issued", 0)),
        ),
        (
            "Certificates — pending issue",
            str(k.get("pending_certificates", 0)),
        ),
    ]


def _plain_body(agent: Agent, k: dict, title: str, lead: str) -> str:
    lines = [title, "", f"Agent: {agent.full_name} ({agent.agent_id})", lead, ""]
    for label, value in _kpi_rows(k):
        lines.append(f"{label}: {value}")
    lines.append("")
    lines.append("This is an automated message from Estithmar.")
    return "\n".join(lines)


def send_agent_portfolio_email(
    agent: Agent,
    *,
    trigger: str = "update",
    extra_lead: str = "",
) -> bool:
    """Send a full KPI email to the agent. Returns True if a send was attempted and mail is configured."""
    if not should_notify_agents():
        return False
    to = (agent.email or "").strip()
    if not to or "@" not in to:
        return False
    if not mail_configured():
        if current_app:
            current_app.logger.info("Agent KPI email skipped (mail not configured).")
        return False
    k = compute_agent_kpis(agent.id)
    if not k:
        return False
    sym, cur = k["currency_symbol"], k["currency_code"]
    lead = (extra_lead or "").strip() or "Your latest portfolio numbers are below."
    subj = f"Estithmar — your portfolio — {_fmt(sym, cur, k.get('total_subscribed', Decimal('0')))}"
    plain = _plain_body(agent, k, "Your portfolio (KPI summary)", lead)
    dash = None
    try:
        dash = url_for("dashboard", _external=True)
    except Exception:
        pass
    html = try_render_transactional(
        audience="Agent",
        title="Portfolio & KPIs",
        intro=(f"Hello {agent.full_name},\n\n{lead}"),
        detail_rows=_kpi_rows(k),
        cta_url=dash,
        cta_label="Open dashboard" if dash else None,
    )
    ok, err = send_email_with_retry(
        to,
        subj,
        plain,
        body_html=html,
        retries=2,
        message_kind="agent_kpi",
        context={"agent_id": agent.id, "trigger": trigger},
    )
    if not ok and current_app:
        current_app.logger.warning("Agent portfolio email failed: %s", err)
    return bool(ok)


def notify_agent_on_member_payment(contribution: Contribution, member: Member) -> None:
    """If enabled, email the member's agent a payment alert and KPI block."""
    if not should_notify_agent_on_payment():
        return
    aid = member.agent_id
    if not aid:
        return
    a = db.session.get(Agent, aid)
    if a is None:
        return
    to = (a.email or "").strip()
    if not to:
        return
    if not mail_configured():
        return
    k = compute_agent_kpis(a.id)
    if not k:
        return
    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    amt = contribution.amount or Decimal("0")
    lead = (
        f"New payment recorded: {member.full_name or member.member_id_display} — "
        f"{_fmt(sym, cur, amt)} (Receipt: {contribution.receipt_no or contribution.id}, date {contribution.date}).\n\n"
        f"Current portfolio snapshot:"
    )
    subj = f"Payment: {sym}{amt:,.2f} {cur} — {a.agent_id}"
    plain = _plain_body(
        a, k, f"New member payment (receipt {contribution.receipt_no or contribution.id})", lead
    )
    dash = None
    try:
        dash = url_for("dashboard", _external=True)
    except Exception:
        pass
    html = try_render_transactional(
        audience="Agent",
        title="Member payment & portfolio",
        intro=f"Hello {a.full_name},\n\n{lead}",
        detail_rows=_kpi_rows(k),
        cta_url=dash,
        cta_label="Open dashboard" if dash else None,
    )
    try:
        ok, err = send_email_with_retry(
            to,
            subj,
            plain,
            body_html=html,
            retries=2,
            message_kind="agent_payment",
            context={"contribution_id": contribution.id, "agent_id": a.id},
        )
        if not ok and current_app:
            current_app.logger.warning("Agent payment email failed: %s", err)
    except Exception:
        if current_app:
            current_app.logger.exception("Agent payment notify error")


def send_kpi_to_all_active_agents() -> dict:
    """Manually from Settings — send a portfolio digest to every active agent with an email. Returns counts."""
    if not should_notify_agents() or not mail_configured():
        return {"sent": 0, "skipped_no_email": 0, "failed": 0, "aborted": True}
    sent = 0
    failed = 0
    agents = (
        Agent.query.filter(Agent.status == "Active")
        .order_by(Agent.full_name.asc(), Agent.id.asc())
        .all()
    )
    skipped = sum(1 for g in agents if not (g.email or "").strip() or "@" not in (g.email or ""))
    for ag in agents:
        to = (ag.email or "").strip()
        if not to or "@" not in to:
            continue
        if send_agent_portfolio_email(ag, trigger="digest", extra_lead="Portfolio update for your team."):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "skipped_no_email": skipped, "failed": failed, "aborted": False}
