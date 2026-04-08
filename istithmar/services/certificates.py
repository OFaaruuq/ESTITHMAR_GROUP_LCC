from __future__ import annotations

from datetime import date
from decimal import Decimal

from istithmar import db
from istithmar.models import ShareCertificate, ShareSubscription, get_or_create_settings, next_certificate_no
from istithmar.services.subscriptions import recompute_subscription_status


def format_certificate_share_quantity(sub: ShareSubscription | None, currency_code: str = "USD") -> str:
    """Number of shares for certificate wording (recorded units, or derived from amount ÷ unit price, or value label)."""
    if sub is None:
        return "—"
    su = sub.share_units_subscribed
    if su is not None and Decimal(str(su)) > 0:
        d = Decimal(str(su))
        t = format(d, "f").rstrip("0").rstrip(".")
        return t or "0"
    pup = sub.share_unit_price
    samt = sub.subscribed_amount or Decimal("0")
    if pup is not None and Decimal(str(pup)) > 0:
        d = (Decimal(str(samt)) / Decimal(str(pup))).quantize(Decimal("0.0001"))
        t = format(d, "f").rstrip("0").rstrip(".")
        return t or "0"
    return f"{float(samt):,.2f} {currency_code}"


def certificate_share_position_detail(
    sub: ShareSubscription | None, currency_symbol: str, currency_code: str
) -> str:
    """Human-readable share basis for certificates/PDF (units @ price, or value note)."""
    if sub is None:
        return "—"
    parts: list[str] = []
    su = sub.share_units_subscribed
    if su is not None and Decimal(str(su)) > 0:
        t = format(Decimal(str(su)), "f").rstrip("0").rstrip(".")
        parts.append(f"{t} units")
    pup = sub.share_unit_price
    if pup is not None and Decimal(str(pup)) > 0:
        parts.append(f"@ {currency_symbol}{float(Decimal(str(pup))):,.2f} {currency_code}")
    if parts:
        return " ".join(parts)
    samt = sub.subscribed_amount or Decimal("0")
    return f"Value basis {currency_symbol}{float(samt):,.2f} {currency_code} (no unit count on record)"


def certificate_stock_of_name(sub: ShareSubscription | None, default_company: str) -> str:
    """Entity name after 'Shares Of Stock Of' — linked investment name when set, else company legal name."""
    if sub and sub.investment and sub.investment.name:
        return sub.investment.name.strip()
    return (default_company or "Istithmar Investment Management").strip()


def issue_certificate(
    subscription_id: int,
    *,
    issued_by_user_id: int | None = None,
    issued_date: date | None = None,
    notes: str | None = None,
    commit: bool = True,
) -> ShareCertificate:
    """Issue a share certificate when the subscription is fully paid and share-confirmed (paid == subscribed)."""
    sub = db.session.get(ShareSubscription, subscription_id)
    if sub is None:
        raise ValueError("Invalid subscription.")
    if sub.status == "Cancelled":
        raise ValueError("Cannot issue certificate for a cancelled subscription.")
    if sub.member.status != "Active":
        raise ValueError("Only active members are certificate-eligible.")

    # Ensure status is up to date before issuing (Active member + Fully Paid + confirmed).
    recompute_subscription_status(sub.id, commit=False)
    if sub.status != "Fully Paid":
        raise ValueError("Certificate can only be issued when the subscription is fully paid.")
    if not sub.is_share_confirmed:
        raise ValueError("Subscription must be confirmed (paid equals subscribed) before issuing a certificate.")
    if sub.paid_total() < (sub.subscribed_amount or 0):
        raise ValueError("Payment records are incomplete for this subscription.")
    settings = get_or_create_settings()
    if settings.get_flag("require_verification_for_certificate"):
        for c in sub.contributions.all():
            if not getattr(c, "verified", False):
                raise ValueError(
                    "All recorded payments for this subscription must be verified before issuing a certificate."
                )
    if sub.certificate is not None and sub.certificate.status == "Issued":
        raise ValueError("A valid certificate already exists for this subscription.")

    cert = ShareCertificate(
        certificate_no=next_certificate_no(),
        subscription_id=sub.id,
        member_id=sub.member_id,
        agent_id=sub.agent_id,
        issued_date=issued_date or date.today(),
        issued_by_user_id=issued_by_user_id,
        status="Issued",
        notes=(notes or "").strip() or None,
    )
    db.session.add(cert)
    if commit:
        db.session.commit()
    return cert


def maybe_auto_issue_certificate(subscription_id: int, *, user_id: int | None) -> bool:
    """Certificate eligibility trigger: run after payments recompute status to Fully Paid / confirmed."""
    settings = get_or_create_settings()
    if not settings.get_flag("auto_issue_certificate"):
        return False
    sub = db.session.get(ShareSubscription, subscription_id)
    if not sub:
        return False
    recompute_subscription_status(sub.id, commit=False)
    if sub.status != "Fully Paid" or not sub.is_share_confirmed:
        return False
    if settings.get_flag("require_verification_for_certificate"):
        for c in sub.contributions.all():
            if not getattr(c, "verified", False):
                return False
    if sub.certificate is not None and sub.certificate.status == "Issued":
        return False
    try:
        issue_certificate(subscription_id, issued_by_user_id=user_id, commit=False)
        return True
    except ValueError:
        return False
