"""Permission keys and resolution (database-backed, least privilege)."""

from __future__ import annotations

from typing import Any

# Back-office roles (route-level coarse access; use role_required with these).
STAFF_ROLES: tuple[str, ...] = ("admin", "operator", "finance")
STAFF_OR_AGENT: tuple[str, ...] = ("admin", "operator", "finance", "agent")

# (key, short label, description, sort_order) — used by ensure_rbac_seed; keys must match routes/templates when wired.
PERMISSION_CATALOG: list[tuple[str, str, str, int]] = [
    # Core
    (
        "core.dashboard",
        "Dashboard",
        "Open the main dashboard and scoped summaries.",
        5,
    ),
    (
        "core.profile",
        "Own profile",
        "View and update the signed-in user profile and password (non-admin).",
        6,
    ),
    # Members
    ("members.view", "Members — list", "List and search members; apply filters and exports that require this.", 20),
    ("members.create", "Members — create", "Register a new member record.", 21),
    ("members.view_detail", "Members — view", "Open a member detail page (read).", 22),
    ("members.edit", "Members — edit", "Update member data and personal fields.", 23),
    ("members.export", "Members — export XLSX", "Export the members list to Excel.", 24),
    ("members.export_pdf", "Members — export PDF", "Export members listing to PDF.", 25),
    (
        "members.documents_upload",
        "Member documents — upload",
        "Upload KYC/attachments for a member.",
        26,
    ),
    (
        "members.documents_download",
        "Member documents — download",
        "Download stored member document files.",
        27,
    ),
    (
        "members.documents_delete",
        "Member documents — delete",
        "Remove a stored document from a member file.",
        28,
    ),
    (
        "members.membership_form",
        "Membership form",
        "View or generate the membership form for a member.",
        29,
    ),
    (
        "members.membership_form_pdf",
        "Membership form — PDF",
        "Download the membership form as a PDF file.",
        30,
    ),
    # Agents
    ("agents.view", "Agents — list", "List agents; search and filter.", 40),
    ("agents.create", "Agents — create", "Add a new agent (including quick-create flows).", 41),
    ("agents.view_detail", "Agents — view", "View an agent’s profile and linked members.", 42),
    ("agents.edit", "Agents — edit", "Update agent data.", 43),
    ("agents.export", "Agents — export", "Export agents to Excel or related bulk extract.", 44),
    # API
    (
        "api.lookup_agent_regions",
        "API — agent regions",
        "Use the agent region lookup API when registering or editing address data.",
        50,
    ),
    # Subscriptions
    (
        "subscriptions.view",
        "Subscriptions — list",
        "List share subscriptions; filter by project or member as allowed.",
        60,
    ),
    (
        "subscriptions.create",
        "Subscriptions — create",
        "Create a new subscription and related intake.",
        61,
    ),
    (
        "subscriptions.view_detail",
        "Subscriptions — view",
        "Open subscription details (read).",
        62,
    ),
    ("subscriptions.edit", "Subscriptions — edit", "Edit subscription and payment plan context.", 63),
    (
        "subscriptions.cancel",
        "Subscriptions — cancel",
        "Cancel or terminate a subscription (policy-aware).",
        64,
    ),
    (
        "subscriptions.set_investment",
        "Subscriptions — set investment",
        "Link a subscription to an investment pool or line.",
        65,
    ),
    (
        "subscriptions.installments",
        "Subscriptions — installments",
        "View and manage installment schedules and adjustments.",
        66,
    ),
    # Certificates
    ("certificates.view", "Certificates — list", "List issued certificates; filter or search.", 80),
    ("certificates.issue", "Certificates — issue", "Issue a new share certificate from a subscription.", 81),
    ("certificates.print", "Certificates — print", "Open print view for a certificate.", 82),
    ("certificates.pdf", "Certificates — PDF", "Download certificate as PDF.", 83),
    ("certificates.revoke", "Certificates — revoke", "Revoke an issued certificate.", 84),
    (
        "certificates.reinstate",
        "Certificates — reinstate",
        "Reinstate a previously revoked certificate.",
        85,
    ),
    # Contributions & payments
    ("contributions.view", "Contributions — list", "List contributions; filters, search, and receipts index.", 100),
    (
        "contributions.create",
        "Contributions — create",
        "Record a new payment or in-kind deposit.",
        101,
    ),
    (
        "contributions.receipt",
        "Contributions — receipt",
        "View/print a contribution receipt (HTML/print).",
        102,
    ),
    (
        "payments.verify",
        "Payments — verify",
        "Mark contribution as verified; drives GL and pool rules when enabled.",
        103,
    ),
    (
        "contributions.unverify",
        "Contributions — unverify",
        "Remove verified status and unwind dependent postings where allowed.",
        104,
    ),
    (
        "contributions.reverse",
        "Contributions — reverse",
        "Reverse a posted or allocated contribution (controlled accounting action).",
        105,
    ),
    (
        "contributions.delete",
        "Contributions — delete",
        "Delete a draft or deletable payment row (irreversible).",
        106,
    ),
    ("contributions.export", "Contributions — export XLSX", "Export contribution lines to Excel.", 107),
    (
        "contributions.export_pdf",
        "Contributions — export PDF",
        "Export contribution list or receipt batch to PDF.",
        108,
    ),
    (
        "invoices.view",
        "Invoices — list & detail",
        "View the invoices list and per-payment invoice pages (contribution-based).",
        109,
    ),
    # Projects
    ("projects.view", "Projects — list", "List projects, filters, and read-only project discovery.", 120),
    ("projects.create", "Projects — create", "Start a new project and baseline budget fields.", 121),
    ("projects.view_detail", "Projects — view", "Open a project read-only or overview.", 122),
    ("projects.edit", "Projects — edit", "Edit project name, status, and operational fields.", 123),
    ("projects.export", "Projects — export", "Export projects to Excel (for planning or review).", 124),
    # Investments
    ("investments.view", "Investments — list", "List company investments; filter and sort.", 140),
    (
        "investments.create",
        "Investments — create",
        "Add a new investment under a project.",
        141,
    ),
    (
        "investments.view_detail",
        "Investments — view",
        "Open investment details and sub-ledgers where permitted.",
        142,
    ),
    (
        "investments.edit",
        "Investments — edit",
        "Update deployment, labels, and operational fields on an investment.",
        143,
    ),
    (
        "investments.delete",
        "Investments — delete",
        "Remove a deletable investment or archive line (irreversible).",
        144,
    ),
    (
        "investments.ledger_snapshot",
        "Investments — ledger snapshot",
        "Trigger or refresh investment ledger snapshot lines.",
        145,
    ),
    (
        "investments.export",
        "Investments — export",
        "Export investment positions and filters to Excel.",
        146,
    ),
    # Profit
    (
        "profit.distribute",
        "Profit — distribute",
        "Run a profit distribution batch; affects members and GL.",
        160,
    ),
    (
        "profit.view",
        "Profit — workbench",
        "Open the profit workbench, previews, and allocation inputs.",
        161,
    ),
    (
        "profit.view_batch",
        "Profit — batch view",
        "View a specific distribution batch, lines, and outcomes.",
        162,
    ),
    ("profit.history", "Profit — history", "Browse past batches and restatement links.", 163),
    (
        "profit.statement",
        "Profit — member statement",
        "View or print a per-member profit statement (staff scope).",
        164,
    ),
    # Users & access control
    ("users.view", "Users — list", "List back-office and portal user accounts.", 180),
    ("users.create", "Users — create", "Create a new app user; send credentials as configured.", 181),
    ("users.edit", "Users — edit", "Edit a user, role, and flags (non-superuser within policy).", 182),
    (
        "users.permissions",
        "Users — permissions hub",
        "Open the role matrix, assignable-roles, and per-user extra grants admin UI.",
        183,
    ),
    # Settings
    (
        "settings.view",
        "Settings — general",
        "View and edit general application, branding, and org settings.",
        200,
    ),
    (
        "settings.notifications",
        "Settings — notifications & mail",
        "Configure email/SMTP, templates, and member/user notifications behavior.",
        201,
    ),
    (
        "settings.payment_methods",
        "Settings — payment methods",
        "Maintain banks, mobile money providers, and public payment copy.",
        202,
    ),
    (
        "settings.database_backup",
        "Settings — database backup",
        "Run a full database backup to the application’s data backup folder (MSSQL .bak or PostgreSQL dump).",
        203,
    ),
    # Reports (per screen + hub)
    ("reports.hub", "Reports — hub", "Open the main reports index.", 220),
    ("reports.monthly", "Reports — monthly", "Run monthly performance and collection reports.", 221),
    (
        "reports.member",
        "Reports — member",
        "Drill a single member’s contribution/position report.",
        222,
    ),
    ("reports.agents", "Reports — agents", "Agent activity, ranking, and exposure reports.", 223),
    (
        "reports.geography",
        "Reports — geography",
        "Regional/territory maps and breakdowns (including agents geography).",
        224,
    ),
    (
        "reports.installments",
        "Reports — installments",
        "Aging, schedule adherence, and installment gap reports.",
        225,
    ),
    (
        "reports.members_financial",
        "Reports — members financial",
        "Cross-member financial exposure and KYC/limits summary (staff).",
        226,
    ),
    (
        "reports.profit_calculation",
        "Reports — profit calculation",
        "Detailed working for profit accrual and policy inputs.",
        227,
    ),
    (
        "reports.profit_summary",
        "Reports — profit summary",
        "Condensed P&L style summary for a period or batch.",
        228,
    ),
    (
        "reports.investments_summary",
        "Reports — investments summary",
        "Aggregate deployment and return by project/instrument.",
        229,
    ),
    ("reports.daily", "Reports — daily", "Intraday/daily collection and position snapshot.", 230),
    (
        "reports.projects_profitability",
        "Reports — project profitability",
        "Project margin and ROI type views.",
        231,
    ),
    (
        "reports.community_model",
        "Reports — community model",
        "Community and pool-level model outputs (governance/limits).",
        232,
    ),
    # Bulk export routes
    ("export.members", "Export — members XLSX", "Call the members XLSX export route.", 240),
    ("export.agents", "Export — agents XLSX", "Call the agents XLSX export route.", 241),
    (
        "export.contributions",
        "Export — contributions XLSX",
        "Call the contributions XLSX export route.",
        242,
    ),
    (
        "export.investments",
        "Export — investments XLSX",
        "Call the investments XLSX export route.",
        243,
    ),
    (
        "export.profit",
        "Export — profit XLSX",
        "Call the profit-distribution XLSX export route.",
        244,
    ),
    ("export.projects", "Export — projects XLSX", "Call the projects XLSX export route.", 245),
    ("export.members_pdf", "Export — members PDF", "Call the members list PDF export.", 246),
    (
        "export.contributions_pdf",
        "Export — contributions PDF",
        "Call the contributions list PDF export.",
        247,
    ),
    # General ledger
    (
        "accounting.view",
        "Accounting — hub",
        "Open the accounting/GL home and read-only overviews where shown.",
        260,
    ),
    (
        "accounting.settings",
        "Accounting — settings",
        "Fiscal/GL options, system accounts, and posting policy toggles.",
        261,
    ),
    (
        "accounting.chart",
        "Accounting — chart of accounts",
        "Create or edit the chart; manage account tree.",
        262,
    ),
    (
        "accounting.ledger",
        "Accounting — account ledger",
        "Drill a single G/L account’s activity.",
        263,
    ),
    (
        "accounting.journal",
        "Accounting — journal (read)",
        "Browse the journal, filters, and entry drill-downs.",
        264,
    ),
    (
        "accounting.journal_void",
        "Accounting — void entry",
        "Void a system or manual journal entry in an open period.",
        265,
    ),
    (
        "accounting.trial_balance",
        "Accounting — trial balance",
        "Run trial balance for a date range/period.",
        266,
    ),
    (
        "accounting.trial_balance_export",
        "Accounting — trial balance export",
        "Download trial balance to CSV/Excel (route-specific).",
        267,
    ),
    (
        "accounting.journal_export",
        "Accounting — journal export",
        "Export the journal to CSV/Excel (route-specific).",
        268,
    ),
    (
        "accounting.manual_entry",
        "Accounting — manual journal",
        "Create and post a balanced manual GL journal.",
        269,
    ),
    # Audit
    (
        "audit.view",
        "Audit log",
        "View the immutable audit log for compliance review.",
        280,
    ),
    (
        "audit.export",
        "Audit log — export",
        "Export the audit log (CSV) with filters (subject to data policy).",
        281,
    ),
    # System / API
    (
        "system.api_notifications_unread",
        "API — header notifications count",
        "Call the small JSON endpoint used for the notification badge in the shell.",
        300,
    ),
    (
        "accounting.close_period",
        "Accounting — close / reopen period",
        "Close or reopen accounting periods; controls posting in closed dates.",
        301,
    ),
    (
        "subscriptions.amend",
        "Subscriptions — amendments",
        "Create or view subscription share/amount amendment history.",
        302,
    ),
    (
        "profit.eligibility",
        "Profit — eligibility (snapshots)",
        "Run or review eligibility snapshots feeding profit distribution.",
        303,
    ),
]


def _keys_from_catalog() -> list[str]:
    return [k for k, _, _, _ in PERMISSION_CATALOG]


def _validate_catalog() -> None:
    keys = _keys_from_catalog()
    if len(keys) < 50:
        raise RuntimeError("PERMISSION_CATALOG should define at least 50 keys.")
    if len(set(keys)) != len(keys):
        raise RuntimeError("PERMISSION_CATALOG has duplicate keys.")


_validate_catalog()


# Not granted to the operator baseline (finance or admin by policy).
_OPERATOR_DENIED = frozenset(
    {
        "users.view",
        "users.create",
        "users.edit",
        "users.permissions",
        "settings.view",
        "settings.notifications",
        "settings.payment_methods",
        "settings.database_backup",
        "payments.verify",
        "contributions.unverify",
        "contributions.reverse",
        "contributions.delete",
        "accounting.settings",
        "accounting.journal_void",
        "accounting.close_period",
        "accounting.manual_entry",
        "profit.distribute",
        "profit.eligibility",
        "investments.delete",
    }
)

class Permission:
    """Stable keys; ``permission_definitions`` rows and routes should use the same string."""

    # Core
    CORE_DASHBOARD = "core.dashboard"
    CORE_PROFILE = "core.profile"
    SYSTEM_API_NOTIFICATIONS_UNREAD = "system.api_notifications_unread"
    API_LOOKUP_AGENT_REGIONS = "api.lookup_agent_regions"
    # Members
    MEMBERS_VIEW = "members.view"
    MEMBERS_CREATE = "members.create"
    MEMBERS_VIEW_DETAIL = "members.view_detail"
    MEMBERS_EDIT = "members.edit"
    MEMBERS_MEMBERSHIP_FORM = "members.membership_form"
    MEMBERS_MEMBERSHIP_FORM_PDF = "members.membership_form_pdf"
    MEMBERS_DOCUMENTS_UPLOAD = "members.documents_upload"
    MEMBERS_DOCUMENTS_DOWNLOAD = "members.documents_download"
    MEMBERS_DOCUMENTS_DELETE = "members.documents_delete"
    # Agents
    AGENTS_VIEW = "agents.view"
    AGENTS_CREATE = "agents.create"
    AGENTS_VIEW_DETAIL = "agents.view_detail"
    AGENTS_EDIT = "agents.edit"
    # Subscriptions
    SUBSCRIPTIONS_VIEW = "subscriptions.view"
    SUBSCRIPTIONS_CREATE = "subscriptions.create"
    SUBSCRIPTIONS_VIEW_DETAIL = "subscriptions.view_detail"
    SUBSCRIPTIONS_EDIT = "subscriptions.edit"
    SUBSCRIPTIONS_INSTALLMENTS = "subscriptions.installments"
    # Certificates
    CERTIFICATES_VIEW = "certificates.view"
    CERTIFICATES_PRINT = "certificates.print"
    CERTIFICATES_PDF = "certificates.pdf"
    # Contributions
    CONTRIBUTIONS_VIEW = "contributions.view"
    CONTRIBUTIONS_CREATE = "contributions.create"
    CONTRIBUTIONS_RECEIPT = "contributions.receipt"
    # Projects
    PROJECTS_VIEW = "projects.view"
    PROJECTS_CREATE = "projects.create"
    PROJECTS_VIEW_DETAIL = "projects.view_detail"
    PROJECTS_EDIT = "projects.edit"
    # Investments
    INVESTMENTS_VIEW = "investments.view"
    INVESTMENTS_CREATE = "investments.create"
    INVESTMENTS_VIEW_DETAIL = "investments.view_detail"
    INVESTMENTS_EDIT = "investments.edit"
    # Invoices
    INVOICES_VIEW = "invoices.view"
    # Payments / contributions (actions)
    PAYMENTS_VERIFY = "payments.verify"
    CONTRIBUTIONS_REVERSE = "contributions.reverse"
    CONTRIBUTIONS_DELETE = "contributions.delete"
    CONTRIBUTIONS_UNVERIFY = "contributions.unverify"
    # Users / RBAC
    USERS_VIEW = "users.view"
    USERS_CREATE = "users.create"
    USERS_EDIT = "users.edit"
    USERS_PERMISSIONS = "users.permissions"
    # Settings
    SETTINGS_VIEW = "settings.view"
    SETTINGS_NOTIFICATIONS = "settings.notifications"
    SETTINGS_PAYMENT_METHODS = "settings.payment_methods"
    SETTINGS_DATABASE_BACKUP = "settings.database_backup"
    # Profit
    PROFIT_VIEW = "profit.view"
    PROFIT_DISTRIBUTE = "profit.distribute"
    PROFIT_HISTORY = "profit.history"
    PROFIT_STATEMENT = "profit.statement"
    INVESTMENTS_DELETE = "investments.delete"
    # GL
    ACCOUNTING_VIEW = "accounting.view"
    ACCOUNTING_SETTINGS = "accounting.settings"
    ACCOUNTING_CHART = "accounting.chart"
    ACCOUNTING_LEDGER = "accounting.ledger"
    ACCOUNTING_JOURNAL = "accounting.journal"
    ACCOUNTING_JOURNAL_VOID = "accounting.journal_void"
    ACCOUNTING_TRIAL_BALANCE = "accounting.trial_balance"
    ACCOUNTING_TRIAL_BALANCE_EXPORT = "accounting.trial_balance_export"
    ACCOUNTING_JOURNAL_EXPORT = "accounting.journal_export"
    ACCOUNTING_MANUAL_ENTRY = "accounting.manual_entry"
    # Reports (hub used as cross-cutting “can open” for report routes)
    REPORTS_HUB = "reports.hub"
    # Audit
    AUDIT_VIEW = "audit.view"
    AUDIT_EXPORT = "audit.export"
    # Exports
    EXPORT_MEMBERS = "export.members"
    EXPORT_AGENTS = "export.agents"
    EXPORT_CONTRIBUTIONS = "export.contributions"
    EXPORT_INVESTMENTS = "export.investments"
    EXPORT_PROFIT = "export.profit"
    EXPORT_PROJECTS = "export.projects"
    EXPORT_MEMBERS_PDF = "export.members_pdf"
    EXPORT_CONTRIBUTIONS_PDF = "export.contributions_pdf"


def default_operator_permission_keys() -> set[str]:
    """Operational staff: most modules without cash-control, GL policy, or identity administration."""
    return set(_keys_from_catalog()) - _OPERATOR_DENIED


def default_finance_permission_keys() -> set[str]:
    """Finance: full operational financial stack; excluding pure user admin (tighten in the matrix as needed)."""
    return set(_keys_from_catalog()) - {
        "users.create",
        "users.edit",
        "users.permissions",
        "settings.database_backup",
    }


def default_agent_permission_keys() -> set[str]:
    """Field agents: day-to-day membership; reports/exports included so role matrix need not list each report key."""
    base = {
        "core.dashboard",
        "core.profile",
        "api.lookup_agent_regions",
        "members.view",
        "members.create",
        "members.view_detail",
        "members.edit",
        "members.membership_form",
        "members.membership_form_pdf",
        "members.documents_upload",
        "members.documents_download",
        "members.documents_delete",
        "subscriptions.view",
        "subscriptions.create",
        "subscriptions.view_detail",
        "subscriptions.edit",
        "subscriptions.installments",
        "certificates.view",
        "certificates.print",
        "certificates.pdf",
        "contributions.view",
        "contributions.create",
        "contributions.receipt",
        "projects.view",
        "projects.view_detail",
        "investments.view",
        "investments.view_detail",
        "invoices.view",
        "profit.history",
        "profit.statement",
        "system.api_notifications_unread",
    }
    all_reports = {k for k, _, _, _ in PERMISSION_CATALOG if k.startswith("reports.") or k.startswith("export.")}
    return base | all_reports


def user_has_permission(user: Any, permission: str) -> bool:
    """True if the user is active and has the permission (role defaults + grants, or superuser)."""
    try:
        from estithmar.rbac import user_has_permission_dbc

        return user_has_permission_dbc(user, permission)
    except Exception:
        return False
