from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask_login import UserMixin

from estithmar import db

PROJECT_STATUSES = [
    ("Planned", "Planned"),
    ("Active", "Active"),
    ("On Hold", "On Hold"),
    ("Completed", "Completed"),
    ("Closed", "Closed"),
]

PROJECT_CATEGORIES = [
    ("real_estate", "Real Estate Projects"),
    ("medical", "Medical Projects"),
    ("trading", "Trading Projects"),
    ("services", "Service Projects"),
    ("partnership", "Partnership Projects"),
    ("agriculture", "Agriculture Projects"),
    ("transport", "Transport Business"),
]

SUBSCRIPTION_STATUSES = [
    ("Pending", "Pending"),
    ("Partially Paid", "Partially Paid"),
    ("Fully Paid", "Fully Paid"),
    ("Cancelled", "Cancelled"),
]

PAYMENT_PLANS = [
    ("full", "Full Payment"),
    ("installment", "Installment"),
]

ELIGIBILITY_POLICIES = [
    ("paid_proportional", "Paid proportional"),
    ("fully_paid_only", "Fully paid only"),
]

INSTALLMENT_STATUSES = [
    ("Pending", "Pending"),
    ("Partially Paid", "Partially Paid"),
    ("Fully Paid", "Fully Paid"),
    ("Overdue", "Overdue"),
    ("Cancelled", "Cancelled"),
]

CERTIFICATE_STATUSES = [
    ("Issued", "Issued"),
    ("Revoked", "Revoked"),
]

INVESTMENT_STATUSES = [
    ("Planned", "Planned"),
    ("Active", "Active"),
    ("Suspended", "Suspended"),
    ("Completed", "Completed"),
    ("Closed", "Closed"),
]

# Suggested cadence for profit reviews (§13.3) — stored on Investment; distributions remain manual.
PROFIT_DISTRIBUTION_FREQUENCIES = [
    ("", "Not set — ad-hoc"),
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("annual", "Annual"),
    ("adhoc", "Ad-hoc only"),
]

USER_ROLES = [
    ("admin", "Admin"),
    ("operator", "Operator"),
    ("agent", "Agent"),
    ("member", "Member"),
]

# People registered under an agent's team (single Member table; kind distinguishes role).
MEMBER_KINDS = [
    ("member", "Member"),
    ("shareholder", "Shareholder"),
    ("investor", "Investor"),
]

MEMBER_GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
]

# Public member code prefix: ``{MEMBER_PUBLIC_ID_PREFIX}-{year}-{seq}`` (e.g. EST-2026-00001).
MEMBER_PUBLIC_ID_PREFIX = "EST"
# Legacy prefix (pre-rename). ``next_member_id`` still considers ``IST-{year}-*`` until rows are migrated.
_LEGACY_MEMBER_PUBLIC_ID_PREFIX = "IST"


def format_member_public_id(member_id: str | None) -> str:
    """Public member code for UI and exports (maps legacy ``IST-*`` to ``EST-*`` until DB is migrated)."""
    if not member_id:
        return ""
    s = str(member_id).strip()
    legacy = f"{_LEGACY_MEMBER_PUBLIC_ID_PREFIX}-"
    if s.startswith(legacy):
        return f"{MEMBER_PUBLIC_ID_PREFIX}-{s[len(legacy):]}"
    return s


# Uploaded identity / KYC files (see MemberDocument).
MEMBER_DOCUMENT_TYPES = [
    ("passport", "Passport"),
    ("national_id", "National ID card"),
    ("drivers_license", "Driver's license"),
    ("proof_of_address", "Proof of address"),
    ("other", "Other document"),
]


class Agent(db.Model):
    __tablename__ = "agents"

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120), index=True)
    region = db.Column(db.String(120))
    territory = db.Column(db.String(120))
    country = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="Active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = db.relationship("Member", backref="agent", lazy="dynamic")
    subscriptions = db.relationship("ShareSubscription", backref="agent", lazy="dynamic")
    certificates = db.relationship("ShareCertificate", backref="agent", lazy="dynamic")

    def members_count(self) -> int:
        return self.members.count()

    def contributions_managed_total(self) -> Decimal:
        from sqlalchemy import func

        q = (
            db.session.query(func.coalesce(func.sum(Contribution.amount), 0))
            .select_from(Contribution)
            .join(Member, Contribution.member_id == Member.id)
            .filter(Member.agent_id == self.id)
        )
        v = q.scalar()
        return Decimal(str(v)) if v is not None else Decimal("0")

    def investments_handled_total(self) -> Decimal:
        """Total contributions collected from members assigned to this agent (managed volume)."""
        return self.contributions_managed_total()

    def total_subscribed_share_value(self) -> Decimal:
        """Sum of subscribed amounts on non-cancelled share subscriptions for this agent's members ('share sales' commitment)."""
        from sqlalchemy import func

        q = (
            db.session.query(func.coalesce(func.sum(ShareSubscription.subscribed_amount), 0))
            .select_from(ShareSubscription)
            .join(Member, ShareSubscription.member_id == Member.id)
            .filter(Member.agent_id == self.id)
            .filter(ShareSubscription.status != "Cancelled")
        )
        v = q.scalar()
        return Decimal(str(v)) if v is not None else Decimal("0")

    def total_share_units_subscribed(self) -> Decimal:
        """Sum of share units recorded on non-cancelled subscriptions (0 if none tracked)."""
        from sqlalchemy import func

        q = (
            db.session.query(func.coalesce(func.sum(ShareSubscription.share_units_subscribed), 0))
            .select_from(ShareSubscription)
            .join(Member, ShareSubscription.member_id == Member.id)
            .filter(Member.agent_id == self.id)
            .filter(ShareSubscription.status != "Cancelled")
        )
        v = q.scalar()
        return Decimal(str(v)) if v is not None else Decimal("0")


class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120), index=True)
    address = db.Column(db.Text)
    national_id = db.Column(db.String(64))
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(32), nullable=True)
    occupation_employer = db.Column(db.String(200), nullable=True)
    next_of_kin_name = db.Column(db.String(200), nullable=True)
    next_of_kin_relationship = db.Column(db.String(100), nullable=True)
    next_of_kin_phone = db.Column(db.String(50), nullable=True)
    next_of_kin_address = db.Column(db.Text, nullable=True)
    join_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False, default="Active")
    member_kind = db.Column(db.String(32), nullable=False, default="member")
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_profit_received = db.Column(db.Numeric(14, 2), nullable=True)
    last_profit_distribution_date = db.Column(db.Date, nullable=True)

    @property
    def member_id_display(self) -> str:
        """Use in templates instead of ``member_id`` so legacy ``IST-*`` shows as ``EST-*``."""
        return format_member_public_id(self.member_id)

    contributions = db.relationship(
        "Contribution", backref="member", lazy="dynamic", cascade="all, delete-orphan"
    )
    subscriptions = db.relationship(
        "ShareSubscription",
        backref="member",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    certificates = db.relationship(
        "ShareCertificate",
        backref="member",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    profit_rows = db.relationship(
        "ProfitDistribution",
        backref="member",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    documents = db.relationship(
        "MemberDocument",
        backref="member",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def contribution_total(self) -> Decimal:
        return sum((c.amount for c in self.contributions), Decimal("0"))

    def orphan_contribution_total(self, verified_only: bool = False) -> Decimal:
        """Payments not linked to a share subscription (real money; global profit pool only)."""
        q = self.contributions.filter(Contribution.subscription_id.is_(None))
        if verified_only:
            q = q.filter(Contribution.verified)
        return sum((c.amount for c in q.all()), Decimal("0"))

    def profit_received_total(self) -> Decimal:
        return sum((p.amount for p in self.profit_rows), Decimal("0"))

    def lifetime_profit_received(self) -> Decimal:
        """Denormalized total when set; otherwise sum of distribution rows (legacy DBs)."""
        if self.total_profit_received is not None:
            return self.total_profit_received
        return self.profit_received_total()

    def eligible_profit_basis(self, verified_only: bool = False) -> Decimal:
        """Total paid amount for profit distribution: subscription basis + unlinked contributions (global pool)."""
        if self.status != "Active":
            return Decimal("0")
        total = Decimal("0")
        for s in self.subscriptions.filter(ShareSubscription.status != "Cancelled").all():
            total += s.eligible_amount_for_profit_distribution(verified_only=verified_only)
        if not get_or_create_settings().get_extra().get("profit_global_fully_paid_only"):
            total += self.orphan_contribution_total(verified_only=verified_only)
        return total

    def eligible_profit_basis_for_investment(
        self, investment_id: int, verified_only: bool = False
    ) -> Decimal:
        """Eligible basis only from share subscriptions linked to this investment (business: pooled by vehicle)."""
        if self.status != "Active":
            return Decimal("0")
        total = Decimal("0")
        for s in self.subscriptions.filter(ShareSubscription.status != "Cancelled").all():
            if s.investment_id is None or s.investment_id != investment_id:
                continue
            total += s.eligible_amount_for_profit_distribution(verified_only=verified_only)
        return total


class PaymentBank(db.Model):
    """Company bank (e.g. Salam Bank, Dahabshiil) — staff-maintained list for contribution recording."""

    __tablename__ = "payment_banks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    accounts = db.relationship(
        "PaymentBankAccount",
        backref="bank",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class PaymentBankAccount(db.Model):
    """A specific account at a company bank (number / IBAN shown to staff when recording transfers)."""

    __tablename__ = "payment_bank_accounts"

    id = db.Column(db.Integer, primary_key=True)
    bank_id = db.Column(db.Integer, db.ForeignKey("payment_banks.id", ondelete="CASCADE"), nullable=False, index=True)
    label = db.Column(db.String(120), nullable=True)
    account_number = db.Column(db.String(120), nullable=False)
    notes = db.Column(db.String(300), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaymentMobileProvider(db.Model):
    """Mobile money brand (e.g. EVC, eDahab, MyCash) for contribution recording."""

    __tablename__ = "payment_mobile_providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Contribution(db.Model):
    __tablename__ = "contributions"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("share_subscriptions.id"), nullable=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    payment_type = db.Column(db.String(20), nullable=False)
    payment_bank_account_id = db.Column(
        db.Integer, db.ForeignKey("payment_bank_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payment_mobile_provider_id = db.Column(
        db.Integer, db.ForeignKey("payment_mobile_providers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    method_ref = db.Column(db.String(120))
    receipt_no = db.Column(db.String(20), unique=True, index=True)
    notes = db.Column(db.Text)
    reversal_of_id = db.Column(db.Integer, db.ForeignKey("contributions.id"), nullable=True, index=True)
    reversal_reason = db.Column(db.String(500), nullable=True)
    reversed_at = db.Column(db.DateTime, nullable=True)
    reversed_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    verified_by = db.relationship("AppUser", backref="verified_contributions", foreign_keys=[verified_by_user_id])
    reversed_by = db.relationship("AppUser", backref="reversed_contributions", foreign_keys=[reversed_by_user_id])
    reversal_of = db.relationship("Contribution", remote_side=[id], uselist=False)
    payment_bank_account = db.relationship("PaymentBankAccount", foreign_keys=[payment_bank_account_id])
    payment_mobile_provider = db.relationship("PaymentMobileProvider", foreign_keys=[payment_mobile_provider_id])

    def payment_channel_detail(self) -> str | None:
        """Extra line for bank account or mobile provider (when linked)."""
        if self.payment_type == "Bank" and self.payment_bank_account_id and self.payment_bank_account:
            acc = self.payment_bank_account
            bk = acc.bank
            if bk:
                lab = (acc.label or "Account").strip()
                return f"{bk.name} · {lab} · {acc.account_number}"
        if self.payment_type == "Mobile" and self.payment_mobile_provider_id and self.payment_mobile_provider:
            return self.payment_mobile_provider.name.strip()
        return None

    def payment_display_label(self) -> str:
        """Short label for lists/receipts: base type plus channel when set."""
        base = {
            "Cash": "Cash",
            "Mobile": "Mobile money",
            "Bank": "Bank transfer",
            "Other": "Other",
        }.get(self.payment_type, self.payment_type or "—")
        det = self.payment_channel_detail()
        if det:
            return f"{base} — {det}"
        return base


class ShareSubscription(db.Model):
    __tablename__ = "share_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    subscription_no = db.Column(db.String(32), unique=True, nullable=False, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=True)
    subscribed_amount = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    share_unit_price = db.Column(db.Numeric(14, 2), nullable=True)
    share_units_subscribed = db.Column(db.Numeric(14, 4), nullable=True)
    payment_plan = db.Column(db.String(20), nullable=False, default="full")
    subscription_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    eligibility_policy = db.Column(
        db.String(30), nullable=False, default="paid_proportional"
    )
    confirmed_at = db.Column(db.DateTime, nullable=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("investments.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    investment = db.relationship("Investment", backref="share_subscriptions", foreign_keys=[investment_id])
    contributions = db.relationship("Contribution", backref="subscription", lazy="dynamic")
    installments = db.relationship(
        "InstallmentPlan",
        backref="subscription",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    certificate = db.relationship(
        "ShareCertificate",
        backref="subscription",
        uselist=False,
        lazy="joined",
        cascade="all, delete-orphan",
    )

    @property
    def is_share_confirmed(self) -> bool:
        """True when subscribed amount is fully paid and the subscription is marked confirmed (confirmed_at set)."""
        return self.status == "Fully Paid" and self.confirmed_at is not None

    def paid_total(self, verified_only: bool = False) -> Decimal:
        """Paid toward this subscription: sum of linked contribution amounts (canonical paid_amount)."""
        q = self.contributions
        if verified_only:
            q = q.filter(Contribution.verified)
        return sum((c.amount for c in q.all()), Decimal("0"))

    def outstanding_balance(self) -> Decimal:
        """Remaining balance vs subscribed_amount (canonical balance; never negative)."""
        bal = (self.subscribed_amount or Decimal("0")) - self.paid_total()
        return bal if bal > 0 else Decimal("0")

    def completion_percent(self) -> Decimal:
        if not self.subscribed_amount or self.subscribed_amount <= 0:
            return Decimal("0")
        pct = (self.paid_total() / self.subscribed_amount) * Decimal("100")
        return min(pct, Decimal("100")).quantize(Decimal("0.01"))

    def eligible_amount_for_profit_distribution(self, verified_only: bool = False) -> Decimal:
        """Basis for profit sharing per subscription policy — always uses real paid money, never promised amount.

        * Organization setting ``profit_global_fully_paid_only``: only Fully Paid subscriptions participate; basis = paid_total().
        * paid_proportional: amounts actually paid toward this subscription (installments included via contributions).
        * fully_paid_only: zero until Fully Paid; then uses paid_total() (real cash), not subscribed_amount.
        * verified_only: count only verified contributions toward paid_total.
        """
        if self.status == "Cancelled":
            return Decimal("0")
        if get_or_create_settings().get_extra().get("profit_global_fully_paid_only"):
            if self.status != "Fully Paid":
                return Decimal("0")
            return self.paid_total(verified_only=verified_only)
        if self.eligibility_policy == "fully_paid_only":
            if self.status == "Fully Paid":
                return self.paid_total(verified_only=verified_only)
            return Decimal("0")
        return self.paid_total(verified_only=verified_only)


class InstallmentPlan(db.Model):
    __tablename__ = "installment_plans"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("share_subscriptions.id"), nullable=False, index=True
    )
    due_date = db.Column(db.Date, nullable=False)
    due_amount = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    paid_amount = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    status = db.Column(db.String(20), nullable=False, default="Pending")
    sequence_no = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def balance(self) -> Decimal:
        bal = (self.due_amount or Decimal("0")) - (self.paid_amount or Decimal("0"))
        return bal if bal > 0 else Decimal("0")


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    project_code = db.Column(db.String(32), unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    project_manager = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Planned")
    total_budget = db.Column(db.Numeric(14, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    investments = db.relationship("Investment", backref="project", lazy="dynamic")

    def total_investment_received(self) -> Decimal:
        return sum((inv.total_amount_invested or Decimal("0") for inv in self.investments), Decimal("0"))


class Investment(db.Model):
    __tablename__ = "investments"

    id = db.Column(db.Integer, primary_key=True)
    investment_code = db.Column(db.String(32), unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    investment_type = db.Column(db.String(120))
    total_amount_invested = db.Column(db.Numeric(14, 2), default=Decimal("0"))
    capital_returned = db.Column(db.Numeric(14, 2), default=Decimal("0"))
    profit_generated = db.Column(db.Numeric(14, 2), default=Decimal("0"))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    project_manager = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Active")
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    profit_entry_date = db.Column(db.Date, nullable=True)
    profit_notes = db.Column(db.Text)
    profit_distribution_frequency = db.Column(db.String(32), nullable=True)
    next_distribution_review_date = db.Column(db.Date, nullable=True)

    created_by = db.relationship("AppUser", foreign_keys=[created_by_user_id])

    distributions = db.relationship(
        "ProfitDistribution",
        backref="investment",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    ledger_entries = db.relationship(
        "InvestmentLedger",
        backref="investment",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    profit_batches = db.relationship(
        "ProfitDistributionBatch",
        backref="investment",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    profit_logs = db.relationship(
        "InvestmentProfitLog",
        backref="investment",
        lazy="dynamic",
    )

    def profit_distributed_to_members(self) -> Decimal:
        """Sum of profit actually distributed to members (ProfitDistribution rows)."""
        from sqlalchemy import func

        v = (
            db.session.query(func.coalesce(func.sum(ProfitDistribution.amount), 0))
            .filter(ProfitDistribution.investment_id == self.id)
            .scalar()
        )
        return Decimal(str(v or 0))

    def profit_undistributed_balance(self) -> Decimal:
        """Recorded profit_generated minus amounts distributed to members."""
        gen = self.profit_generated or Decimal("0")
        return gen - self.profit_distributed_to_members()


class InvestmentProfitLog(db.Model):
    """Audit trail when total profit generated is recorded or updated (manual entry)."""

    __tablename__ = "investment_profit_logs"

    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("investments.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    entry_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InvestmentLedger(db.Model):
    __tablename__ = "investment_ledgers"

    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("investments.id"), nullable=False, index=True)
    capital_invested = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    capital_returned = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    profit_generated = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    profit_distributed = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    profit_undistributed = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProfitDistributionBatch(db.Model):
    __tablename__ = "profit_distribution_batches"

    id = db.Column(db.Integer, primary_key=True)
    batch_no = db.Column(db.String(32), unique=True, nullable=False, index=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("investments.id"), nullable=False, index=True)
    distribution_date = db.Column(db.Date, nullable=False, default=date.today)
    total_profit_input = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    total_profit_distributed = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    policy_used = db.Column(db.String(30), nullable=False, default="paid_proportional")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rows = db.relationship(
        "ProfitDistribution",
        backref="batch",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    snapshots = db.relationship(
        "EligibilitySnapshot",
        backref="batch",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class ProfitDistribution(db.Model):
    __tablename__ = "profit_distributions"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(
        db.Integer, db.ForeignKey("profit_distribution_batches.id"), nullable=True, index=True
    )
    investment_id = db.Column(db.Integer, db.ForeignKey("investments.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    eligible_amount_basis = db.Column(db.Numeric(14, 2))
    share_percentage = db.Column(db.Numeric(10, 6))
    distribution_date = db.Column(db.Date, nullable=False, default=date.today)
    profit_pool_amount = db.Column(db.Numeric(14, 2))
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)

    created_by = db.relationship("AppUser", foreign_keys=[created_by_user_id])


class EligibilitySnapshot(db.Model):
    __tablename__ = "eligibility_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(
        db.Integer, db.ForeignKey("profit_distribution_batches.id"), nullable=False, index=True
    )
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    eligible_amount = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    ownership_pct = db.Column(db.Numeric(10, 6), nullable=False, default=Decimal("0"))
    reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ShareCertificate(db.Model):
    __tablename__ = "share_certificates"

    id = db.Column(db.Integer, primary_key=True)
    certificate_no = db.Column(db.String(32), unique=True, nullable=False, index=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("share_subscriptions.id"), nullable=False, unique=True, index=True
    )
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=True)
    issued_date = db.Column(db.Date, nullable=False, default=date.today)
    issued_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Issued")
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    issued_by = db.relationship("AppUser", backref="issued_certificates", foreign_keys=[issued_by_user_id])


class MemberDocument(db.Model):
    """Scanned or uploaded identity / supporting documents for a member (passport, ID, etc.)."""

    __tablename__ = "member_documents"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    document_type = db.Column(db.String(40), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)

    uploaded_by = db.relationship("AppUser", foreign_keys=[uploaded_by_user_id])


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(120), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppUser(UserMixin, db.Model):
    __tablename__ = "app_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    profile_image = db.Column(db.String(255))
    role = db.Column(db.String(20), nullable=False, default="operator")
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    agent = db.relationship("Agent", backref="users", foreign_keys=[agent_id])
    member = db.relationship("Member", backref="app_users", foreign_keys=[member_id])


class AppSettings(db.Model):
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)
    currency_code = db.Column(db.String(10), default="USD")
    currency_symbol = db.Column(db.String(8), default="$")
    contribution_rules = db.Column(db.Text)
    profit_rules = db.Column(db.Text)
    extra_json = db.Column(db.Text)

    def get_extra(self) -> dict[str, Any]:
        if not self.extra_json:
            return {}
        try:
            data = json.loads(self.extra_json)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def set_extra(self, data: dict[str, Any]) -> None:
        self.extra_json = json.dumps(data)

    def get_flag(self, key: str, default: bool = False) -> bool:
        return bool(self.get_extra().get(key, default))


class SubscriptionAmendment(db.Model):
    __tablename__ = "subscription_amendments"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("share_subscriptions.id"), nullable=False, index=True
    )
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    old_values_json = db.Column(db.Text, nullable=False)
    new_values_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    subscription = db.relationship("ShareSubscription", backref="amendments")
    changed_by = db.relationship("AppUser", foreign_keys=[changed_by_user_id])


class AccountingPeriodClose(db.Model):
    __tablename__ = "accounting_period_closes"

    id = db.Column(db.Integer, primary_key=True)
    close_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    notes = db.Column(db.String(500), nullable=True)
    closed_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    closed_by = db.relationship("AppUser", foreign_keys=[closed_by_user_id])


class ReportSchedule(db.Model):
    __tablename__ = "report_schedules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    report_key = db.Column(db.String(64), nullable=False, index=True)
    frequency = db.Column(db.String(20), nullable=False, default="weekly")
    recipients = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    next_run_at = db.Column(db.DateTime, nullable=True, index=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(30), nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.relationship("AppUser", foreign_keys=[created_by_user_id])


class NotificationDeliveryLog(db.Model):
    __tablename__ = "notification_delivery_logs"

    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(20), nullable=False)  # email | whatsapp
    recipient = db.Column(db.String(200), nullable=False, index=True)
    subject = db.Column(db.String(200), nullable=True)
    message_kind = db.Column(db.String(40), nullable=True)  # member_event | report_schedule
    success = db.Column(db.Boolean, nullable=False, default=False, index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=1)
    error = db.Column(db.String(500), nullable=True)
    context_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


def _member_id_seq_suffix(member_id: str | None) -> int:
    if not member_id:
        return 0
    try:
        return int(member_id.split("-")[-1])
    except (ValueError, IndexError):
        return 0


def next_member_id() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"{MEMBER_PUBLIC_ID_PREFIX}-{year}-"
    legacy_prefix = f"{_LEGACY_MEMBER_PUBLIC_ID_PREFIX}-{year}-"
    last_new = (
        Member.query.filter(Member.member_id.like(f"{prefix}%"))
        .order_by(Member.member_id.desc())
        .first()
    )
    last_legacy = (
        Member.query.filter(Member.member_id.like(f"{legacy_prefix}%"))
        .order_by(Member.member_id.desc())
        .first()
    )
    n = max(_member_id_seq_suffix(last_new.member_id if last_new else None), _member_id_seq_suffix(last_legacy.member_id if last_legacy else None)) + 1
    return f"{prefix}{n:05d}"


def next_agent_id() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"AGT-{year}-"
    last = (
        Agent.query.filter(Agent.agent_id.like(f"{prefix}%"))
        .order_by(Agent.agent_id.desc())
        .first()
    )
    if last:
        try:
            n = int(last.agent_id.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def next_project_code() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"PRJ-{year}-"
    last = (
        Project.query.filter(Project.project_code.isnot(None))
        .filter(Project.project_code.like(f"{prefix}%"))
        .order_by(Project.project_code.desc())
        .first()
    )
    if last and last.project_code:
        try:
            n = int(last.project_code.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def next_investment_code() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"INV-{year}-"
    last = (
        Investment.query.filter(Investment.investment_code.isnot(None))
        .filter(Investment.investment_code.like(f"{prefix}%"))
        .order_by(Investment.investment_code.desc())
        .first()
    )
    if last and last.investment_code:
        try:
            n = int(last.investment_code.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def next_receipt_no() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"RCP-{year}-"
    last = (
        Contribution.query.filter(Contribution.receipt_no.like(f"{prefix}%"))
        .order_by(Contribution.receipt_no.desc())
        .first()
    )
    if last and last.receipt_no:
        try:
            n = int(last.receipt_no.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def next_subscription_no() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"SUB-{year}-"
    last = (
        ShareSubscription.query.filter(ShareSubscription.subscription_no.like(f"{prefix}%"))
        .order_by(ShareSubscription.subscription_no.desc())
        .first()
    )
    if last and last.subscription_no:
        try:
            n = int(last.subscription_no.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def next_certificate_no() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"CER-{year}-"
    last = (
        ShareCertificate.query.filter(ShareCertificate.certificate_no.like(f"{prefix}%"))
        .order_by(ShareCertificate.certificate_no.desc())
        .first()
    )
    if last and last.certificate_no:
        try:
            n = int(last.certificate_no.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def next_profit_batch_no() -> str:
    from datetime import datetime as dt

    year = dt.utcnow().year
    prefix = f"PB-{year}-"
    last = (
        ProfitDistributionBatch.query.filter(ProfitDistributionBatch.batch_no.like(f"{prefix}%"))
        .order_by(ProfitDistributionBatch.batch_no.desc())
        .first()
    )
    if last and last.batch_no:
        try:
            n = int(last.batch_no.split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"{prefix}{n:05d}"


def get_or_create_settings() -> AppSettings:
    row = db.session.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.session.add(row)
        db.session.commit()
    return row
