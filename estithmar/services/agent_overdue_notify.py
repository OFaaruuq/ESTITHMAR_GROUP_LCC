"""Email agents when their assigned members have overdue installments."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import current_app, url_for

from estithmar.models import Agent, NotificationDeliveryLog, get_or_create_settings
from estithmar.services.agent_collections import collect_agent_overdue_members, summarize_agent_overdue
from estithmar.services.agent_email_html import try_render_agent_overdue_digest_html
from estithmar.services.agent_notify import should_notify_agents
from estithmar.services.email_html import try_render_transactional
from estithmar.services.notifications import mail_configured, send_email_with_retry


def _ex() -> dict:
    return get_or_create_settings().get_extra()


def should_notify_agent_overdue_digest() -> bool:
    if not should_notify_agents():
        return False
    return bool(_ex().get("notify_agent_overdue_digest", True))


def agent_overdue_cooldown_days() -> int:
    return max(1, int(_ex().get("agent_overdue_cooldown_days") or 1))


def _digest_sent_recently(agent_id: int, *, as_of: datetime | None = None) -> bool:
    cooldown = agent_overdue_cooldown_days()
    now = as_of or datetime.utcnow()
    since = now - timedelta(days=cooldown)
    logs = (
        NotificationDeliveryLog.query.filter(
            NotificationDeliveryLog.message_kind == "agent_overdue_digest",
            NotificationDeliveryLog.success.is_(True),
            NotificationDeliveryLog.created_at >= since,
        )
        .order_by(NotificationDeliveryLog.created_at.desc())
        .limit(200)
        .all()
    )
    aid = str(agent_id)
    for log in logs:
        if not log.context_json:
            continue
        try:
            ctx = json.loads(log.context_json)
        except Exception:
            continue
        if str(ctx.get("agent_id")) == aid:
            return True
    return False


def _fmt(sym: str, cur: str, d: Decimal) -> str:
    return f"{sym}{(d or Decimal('0')):,.2f} {cur}"


def _plain_body(agent: Agent, members: list[dict], sym: str, cur: str, summary: dict) -> str:
    lines = [
        "Members with overdue installments — collection follow-up",
        "",
        f"Agent: {agent.full_name} ({agent.agent_id})",
        f"Members to call: {summary.get('member_count', 0)}",
        f"Overdue balance: {_fmt(sym, cur, summary.get('overdue_balance', Decimal('0')))}",
        "",
    ]
    for item in members:
        m = item["member"]
        phone = (m.phone or "").strip() or "—"
        email = (m.email or "").strip() or "—"
        lines.append(
            f"- {m.full_name or m.member_id_display} · "
            f"{_fmt(sym, cur, item['overdue_balance'])} · "
            f"{item['overdue_row_count']} row(s) · "
            f"{item['max_days_late']} day(s) late · "
            f"Phone: {phone} · Email: {email}"
        )
    lines.extend(["", "This is an automated message from Estithmar."])
    return "\n".join(lines)


def send_agent_overdue_digest_email(
    agent: Agent,
    members: list[dict] | None = None,
    *,
    trigger: str = "scheduled",
    force: bool = False,
) -> bool:
    """Email one agent a list of overdue members assigned to them."""
    if not force and not should_notify_agent_overdue_digest():
        return False
    to = (agent.email or "").strip()
    if not to or "@" not in to:
        return False
    if not mail_configured():
        if current_app:
            current_app.logger.info("Agent overdue digest skipped (mail not configured).")
        return False

    if members is None:
        members = collect_agent_overdue_members(agent.id, recompute=False)
    if not members:
        return False

    settings = get_or_create_settings()
    sym = settings.currency_symbol or "$"
    cur = settings.currency_code or "USD"
    summary = summarize_agent_overdue(agent.id)

    subj = (
        f"Collection follow-up — {summary['member_count']} overdue member(s) — {agent.agent_id}"
    )
    lead = (
        f"You have {summary['member_count']} assigned member(s) with overdue installments "
        f"totalling {_fmt(sym, cur, summary['overdue_balance'])}. "
        "Please contact them to collect payment."
    )
    plain = _plain_body(agent, members, sym, cur, summary)

    collections_url = None
    try:
        collections_url = url_for("collections_overdue_members", _external=True)
    except Exception:
        pass

    intro = f"Hello {agent.full_name},\n\n{lead}"
    html = try_render_agent_overdue_digest_html(
        agent,
        members,
        summary=summary,
        sym=sym,
        cur=cur,
        title="Overdue members — call list",
        intro=intro,
        cta_url=collections_url,
        cta_label="Open overdue members" if collections_url else None,
    )
    if not html:
        detail_rows = []
        for item in members[:25]:
            m = item["member"]
            detail_rows.append(
                (
                    m.full_name or m.member_id_display,
                    f"{_fmt(sym, cur, item['overdue_balance'])} · {item['max_days_late']}d late",
                )
            )
        html = try_render_transactional(
            audience="Agent",
            title="Overdue members — call list",
            intro=intro,
            detail_rows=detail_rows,
            cta_url=collections_url,
            cta_label="Open overdue members" if collections_url else None,
        )

    ok, err = send_email_with_retry(
        to,
        subj,
        plain,
        body_html=html,
        retries=2,
        message_kind="agent_overdue_digest",
        context={"agent_id": agent.id, "trigger": trigger, "member_count": summary["member_count"]},
    )
    if not ok and current_app:
        current_app.logger.warning("Agent overdue digest failed for %s: %s", agent.agent_id, err)
    return bool(ok)


def run_agent_overdue_reminders(*, as_of: date | None = None, force: bool = False) -> dict:
    """Send overdue-member digest emails to each active agent with overdue portfolio."""
    if not force and not should_notify_agent_overdue_digest():
        return {"sent": 0, "skipped": 0, "failed": 0, "empty": 0, "aborted": True}

    if not mail_configured():
        return {"sent": 0, "skipped": 0, "failed": 0, "empty": 0, "aborted": True}

    sent = skipped = failed = empty = 0
    agents = (
        Agent.query.filter(Agent.status == "Active")
        .order_by(Agent.full_name.asc(), Agent.id.asc())
        .all()
    )

    for agent in agents:
        to = (agent.email or "").strip()
        if not to or "@" not in to:
            skipped += 1
            continue
        members = collect_agent_overdue_members(agent.id, as_of=as_of, recompute=False)
        if not members:
            empty += 1
            continue
        if not force and _digest_sent_recently(agent.id):
            skipped += 1
            continue
        if send_agent_overdue_digest_email(agent, members, trigger="scheduled", force=force):
            sent += 1
        else:
            failed += 1

    return {
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "empty": empty,
        "aborted": False,
    }


def send_overdue_digest_to_all_agents(*, force: bool = True) -> dict:
    """Manual send from Settings — one digest per agent with overdue members."""
    if not mail_configured():
        return {"sent": 0, "skipped": 0, "failed": 0, "empty": 0, "aborted": True}
    sent = skipped = failed = empty = 0
    agents = Agent.query.filter(Agent.status == "Active").order_by(Agent.full_name.asc()).all()
    for agent in agents:
        to = (agent.email or "").strip()
        if not to or "@" not in to:
            skipped += 1
            continue
        members = collect_agent_overdue_members(agent.id, recompute=False)
        if not members:
            empty += 1
            continue
        if send_agent_overdue_digest_email(agent, members, trigger="manual", force=force):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "skipped": skipped, "failed": failed, "empty": empty, "aborted": False}
