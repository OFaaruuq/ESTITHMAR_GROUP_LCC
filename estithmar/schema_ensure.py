"""Add columns introduced after first deploy (when migrations are not run)."""

from __future__ import annotations

from sqlalchemy import inspect, text

from estithmar import db


def ensure_app_schema() -> None:
    """Best-effort ALTER TABLE for existing databases (PostgreSQL / SQL Server)."""
    engine = db.engine
    if engine is None:
        return
    dialect = engine.dialect.name
    insp = inspect(engine)

    def _has_column(table: str, col: str) -> bool:
        try:
            cols = insp.get_columns(table)
        except Exception:
            return False
        return any(c.get("name") == col for c in cols)

    if not _has_column("members", "email"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE members ADD COLUMN email VARCHAR(120)"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE members ADD email NVARCHAR(120) NULL"))
        else:
            db.session.execute(text("ALTER TABLE members ADD COLUMN email VARCHAR(120)"))
        db.session.commit()

    if not _has_column("app_users", "member_id"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN member_id INTEGER"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD member_id INT NULL"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN member_id INTEGER"))
        db.session.commit()

    if not _has_column("app_users", "last_login_at"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_login_at TIMESTAMP"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD last_login_at DATETIME2 NULL"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_login_at TIMESTAMP"))
        db.session.commit()

    if not _has_column("app_users", "last_seen_at"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_seen_at TIMESTAMP"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD last_seen_at DATETIME2 NULL"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_seen_at TIMESTAMP"))
        db.session.commit()

    if not _has_column("app_users", "last_seen_ip"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_seen_ip VARCHAR(64)"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD last_seen_ip NVARCHAR(64) NULL"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_seen_ip VARCHAR(64)"))
        db.session.commit()

    if not _has_column("app_users", "last_seen_user_agent"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_seen_user_agent VARCHAR(255)"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD last_seen_user_agent NVARCHAR(255) NULL"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN last_seen_user_agent VARCHAR(255)"))
        db.session.commit()

    if not _has_column("app_users", "session_version"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD session_version INT NOT NULL CONSTRAINT DF_app_users_session_version DEFAULT 1"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1"))
        db.session.commit()

    if not _has_column("agents", "email"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE agents ADD COLUMN email VARCHAR(120)"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE agents ADD email NVARCHAR(120) NULL"))
        else:
            db.session.execute(text("ALTER TABLE agents ADD COLUMN email VARCHAR(120)"))
        db.session.commit()

    def _add_members_col(name: str, pg: str, mssql: str, fallback: str) -> None:
        nonlocal insp
        insp = inspect(engine)
        if _has_column("members", name):
            return
        if dialect == "postgresql":
            db.session.execute(text(pg))
        elif "mssql" in dialect:
            db.session.execute(text(mssql))
        else:
            db.session.execute(text(fallback))
        db.session.commit()

    _add_members_col(
        "date_of_birth",
        "ALTER TABLE members ADD COLUMN date_of_birth DATE",
        "ALTER TABLE members ADD date_of_birth DATE NULL",
        "ALTER TABLE members ADD COLUMN date_of_birth DATE",
    )
    _add_members_col(
        "gender",
        "ALTER TABLE members ADD COLUMN gender VARCHAR(32)",
        "ALTER TABLE members ADD gender NVARCHAR(32) NULL",
        "ALTER TABLE members ADD COLUMN gender VARCHAR(32)",
    )
    _add_members_col(
        "occupation_employer",
        "ALTER TABLE members ADD COLUMN occupation_employer VARCHAR(200)",
        "ALTER TABLE members ADD occupation_employer NVARCHAR(200) NULL",
        "ALTER TABLE members ADD COLUMN occupation_employer VARCHAR(200)",
    )
    _add_members_col(
        "next_of_kin_name",
        "ALTER TABLE members ADD COLUMN next_of_kin_name VARCHAR(200)",
        "ALTER TABLE members ADD next_of_kin_name NVARCHAR(200) NULL",
        "ALTER TABLE members ADD COLUMN next_of_kin_name VARCHAR(200)",
    )
    _add_members_col(
        "next_of_kin_relationship",
        "ALTER TABLE members ADD COLUMN next_of_kin_relationship VARCHAR(100)",
        "ALTER TABLE members ADD next_of_kin_relationship NVARCHAR(100) NULL",
        "ALTER TABLE members ADD COLUMN next_of_kin_relationship VARCHAR(100)",
    )
    _add_members_col(
        "next_of_kin_phone",
        "ALTER TABLE members ADD COLUMN next_of_kin_phone VARCHAR(50)",
        "ALTER TABLE members ADD next_of_kin_phone NVARCHAR(50) NULL",
        "ALTER TABLE members ADD COLUMN next_of_kin_phone VARCHAR(50)",
    )
    _add_members_col(
        "next_of_kin_address",
        "ALTER TABLE members ADD COLUMN next_of_kin_address TEXT",
        "ALTER TABLE members ADD next_of_kin_address NVARCHAR(MAX) NULL",
        "ALTER TABLE members ADD COLUMN next_of_kin_address TEXT",
    )

    _ensure_member_documents_table(engine, dialect, insp)
    _ensure_audit_actor_columns(engine, dialect, insp)
    _ensure_user_session_log_schema(engine, dialect)
    _ensure_login_otp_challenges_schema(engine, dialect, insp)
    _ensure_payment_options_schema(engine, dialect)
    _ensure_finops_extensions_schema(engine, dialect)
    _ensure_rbac_schema(engine, dialect, insp)


def _ensure_user_session_log_schema(engine, dialect: str) -> None:
    insp = inspect(engine)

    def _has_table(name: str) -> bool:
        try:
            return insp.has_table(name)
        except Exception:
            return False

    if _has_table("user_session_logs"):
        return

    if dialect == "postgresql":
        db.session.execute(
            text(
                """
                CREATE TABLE user_session_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES app_users(id),
                    login_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP NULL,
                    logout_at TIMESTAMP NULL,
                    ip_address VARCHAR(64) NULL,
                    user_agent VARCHAR(255) NULL,
                    was_forced_logout BOOLEAN NOT NULL DEFAULT false,
                    ended_reason VARCHAR(32) NULL
                )
                """
            )
        )
    elif "mssql" in dialect:
        db.session.execute(
            text(
                """
                CREATE TABLE user_session_logs (
                    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    user_id INT NOT NULL,
                    login_at DATETIME2 NOT NULL CONSTRAINT DF_usl_login_at DEFAULT SYSUTCDATETIME(),
                    last_seen_at DATETIME2 NULL,
                    logout_at DATETIME2 NULL,
                    ip_address NVARCHAR(64) NULL,
                    user_agent NVARCHAR(255) NULL,
                    was_forced_logout BIT NOT NULL CONSTRAINT DF_usl_forced DEFAULT 0,
                    ended_reason NVARCHAR(32) NULL,
                    CONSTRAINT FK_usl_user FOREIGN KEY (user_id) REFERENCES app_users(id)
                )
                """
            )
        )
    else:
        db.session.execute(
            text(
                """
                CREATE TABLE user_session_logs (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES app_users(id),
                    login_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP NULL,
                    logout_at TIMESTAMP NULL,
                    ip_address VARCHAR(64) NULL,
                    user_agent VARCHAR(255) NULL,
                    was_forced_logout INTEGER NOT NULL DEFAULT 0,
                    ended_reason VARCHAR(32) NULL
                )
                """
            )
        )
    db.session.execute(text("CREATE INDEX ix_user_session_logs_user_id ON user_session_logs (user_id)"))
    db.session.execute(text("CREATE INDEX ix_user_session_logs_login_at ON user_session_logs (login_at)"))
    db.session.execute(text("CREATE INDEX ix_user_session_logs_last_seen_at ON user_session_logs (last_seen_at)"))
    db.session.commit()


def _ensure_login_otp_challenges_schema(engine, dialect: str, insp) -> None:
    def _has_table(name: str) -> bool:
        try:
            return insp.has_table(name)
        except Exception:
            return False

    if _has_table("login_otp_challenges"):
        return

    if dialect == "postgresql":
        db.session.execute(
            text(
                """
                CREATE TABLE login_otp_challenges (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES app_users(id),
                    nonce VARCHAR(64) NOT NULL UNIQUE,
                    code_hash VARCHAR(256) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    consumed_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    client_ip VARCHAR(64) NULL,
                    next_path VARCHAR(300) NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )
    elif "mssql" in dialect:
        db.session.execute(
            text(
                """
                CREATE TABLE login_otp_challenges (
                    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    user_id INT NOT NULL,
                    nonce NVARCHAR(64) NOT NULL,
                    code_hash NVARCHAR(256) NOT NULL,
                    expires_at DATETIME2 NOT NULL,
                    consumed_at DATETIME2 NULL,
                    created_at DATETIME2 NOT NULL CONSTRAINT DF_lotc_created DEFAULT SYSUTCDATETIME(),
                    client_ip NVARCHAR(64) NULL,
                    next_path NVARCHAR(300) NULL,
                    attempt_count INT NOT NULL CONSTRAINT DF_lotc_attempts DEFAULT 0,
                    CONSTRAINT FK_lotc_user FOREIGN KEY (user_id) REFERENCES app_users(id)
                )
                """
            )
        )
    else:
        db.session.execute(
            text(
                """
                CREATE TABLE login_otp_challenges (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES app_users(id),
                    nonce VARCHAR(64) NOT NULL UNIQUE,
                    code_hash VARCHAR(256) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    consumed_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    client_ip VARCHAR(64) NULL,
                    next_path VARCHAR(300) NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )
    if "mssql" in dialect:
        for stmt in (
            "CREATE NONCLUSTERED INDEX [ix_login_otp_challenges_user_id] "
            "ON [dbo].[login_otp_challenges] ([user_id])",
            "CREATE NONCLUSTERED INDEX [ix_login_otp_challenges_expires_at] "
            "ON [dbo].[login_otp_challenges] ([expires_at])",
            "CREATE NONCLUSTERED INDEX [ix_login_otp_challenges_consumed_at] "
            "ON [dbo].[login_otp_challenges] ([consumed_at])",
            "CREATE UNIQUE NONCLUSTERED INDEX [ix_login_otp_challenges_nonce] "
            "ON [dbo].[login_otp_challenges] ([nonce])",
        ):
            try:
                db.session.execute(text(stmt))
            except Exception:
                pass
    else:
        for stmt in (
            "CREATE INDEX IF NOT EXISTS ix_login_otp_challenges_user_id ON login_otp_challenges (user_id);",
            "CREATE INDEX IF NOT EXISTS ix_login_otp_challenges_expires_at ON login_otp_challenges (expires_at);",
            "CREATE INDEX IF NOT EXISTS ix_login_otp_challenges_consumed_at ON login_otp_challenges (consumed_at);",
        ):
            try:
                db.session.execute(text(stmt))
            except Exception:
                pass
    db.session.commit()


def _ensure_audit_actor_columns(engine, dialect: str, insp) -> None:
    def _has_col(table: str, col: str) -> bool:
        try:
            return any(c.get("name") == col for c in insp.get_columns(table))
        except Exception:
            return False

    if not _has_col("audit_logs", "actor_user_id"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN actor_user_id INTEGER"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE audit_logs ADD actor_user_id INT NULL"))
        else:
            db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN actor_user_id INTEGER"))
        db.session.commit()

    if not _has_col("audit_logs", "actor_username"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN actor_username VARCHAR(64)"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE audit_logs ADD actor_username NVARCHAR(64) NULL"))
        else:
            db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN actor_username VARCHAR(64)"))
        db.session.commit()


def _ensure_payment_options_schema(engine, dialect: str) -> None:
    """Banks, bank accounts, mobile providers, and contribution FK columns."""
    insp = inspect(engine)

    def _has_table(name: str) -> bool:
        try:
            return insp.has_table(name)
        except Exception:
            return False

    def _has_col(table: str, col: str) -> bool:
        try:
            return any(c.get("name") == col for c in insp.get_columns(table))
        except Exception:
            return False

    if not _has_table("payment_banks"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_banks (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(120) NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_banks (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        name NVARCHAR(120) NOT NULL,
                        sort_order INT NOT NULL CONSTRAINT DF_payment_banks_sort DEFAULT 0,
                        is_active BIT NOT NULL CONSTRAINT DF_payment_banks_active DEFAULT 1,
                        created_at DATETIME2 NULL CONSTRAINT DF_payment_banks_created DEFAULT SYSUTCDATETIME()
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_banks (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(120) NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.commit()
        insp = inspect(engine)

    if not _has_table("payment_bank_accounts"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_bank_accounts (
                        id SERIAL PRIMARY KEY,
                        bank_id INTEGER NOT NULL REFERENCES payment_banks(id) ON DELETE CASCADE,
                        label VARCHAR(120),
                        account_number VARCHAR(120) NOT NULL,
                        notes VARCHAR(300),
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.execute(text("CREATE INDEX ix_payment_bank_accounts_bank_id ON payment_bank_accounts (bank_id)"))
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_bank_accounts (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        bank_id INT NOT NULL,
                        label NVARCHAR(120) NULL,
                        account_number NVARCHAR(120) NOT NULL,
                        notes NVARCHAR(300) NULL,
                        sort_order INT NOT NULL CONSTRAINT DF_pba_sort DEFAULT 0,
                        is_active BIT NOT NULL CONSTRAINT DF_pba_active DEFAULT 1,
                        created_at DATETIME2 NULL CONSTRAINT DF_pba_created DEFAULT SYSUTCDATETIME(),
                        CONSTRAINT FK_pba_bank FOREIGN KEY (bank_id) REFERENCES payment_banks(id) ON DELETE CASCADE
                    )
                    """
                )
            )
            db.session.execute(text("CREATE INDEX ix_payment_bank_accounts_bank_id ON payment_bank_accounts (bank_id)"))
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_bank_accounts (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        bank_id INTEGER NOT NULL REFERENCES payment_banks(id) ON DELETE CASCADE,
                        label VARCHAR(120),
                        account_number VARCHAR(120) NOT NULL,
                        notes VARCHAR(300),
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.execute(text("CREATE INDEX ix_payment_bank_accounts_bank_id ON payment_bank_accounts (bank_id)"))
        db.session.commit()
        insp = inspect(engine)

    if not _has_table("payment_mobile_providers"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_mobile_providers (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(120) NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_mobile_providers (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        name NVARCHAR(120) NOT NULL,
                        sort_order INT NOT NULL CONSTRAINT DF_pmp_sort DEFAULT 0,
                        is_active BIT NOT NULL CONSTRAINT DF_pmp_active DEFAULT 1,
                        created_at DATETIME2 NULL CONSTRAINT DF_pmp_created DEFAULT SYSUTCDATETIME()
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE payment_mobile_providers (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(120) NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.commit()
        insp = inspect(engine)

    if _has_table("contributions") and not _has_col("contributions", "payment_bank_account_id"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE contributions ADD COLUMN payment_bank_account_id INTEGER"))
            db.session.execute(
                text(
                    "ALTER TABLE contributions ADD CONSTRAINT fk_contrib_pba "
                    "FOREIGN KEY (payment_bank_account_id) REFERENCES payment_bank_accounts(id) ON DELETE SET NULL"
                )
            )
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE contributions ADD payment_bank_account_id INT NULL"))
            db.session.execute(
                text(
                    "ALTER TABLE contributions ADD CONSTRAINT FK_contributions_pba "
                    "FOREIGN KEY (payment_bank_account_id) REFERENCES payment_bank_accounts(id) ON DELETE SET NULL"
                )
            )
        else:
            db.session.execute(text("ALTER TABLE contributions ADD COLUMN payment_bank_account_id INTEGER"))
        try:
            db.session.execute(
                text("CREATE INDEX ix_contributions_payment_bank_account_id ON contributions (payment_bank_account_id)")
            )
        except Exception:
            pass
        db.session.commit()
        insp = inspect(engine)

    if _has_table("contributions") and not _has_col("contributions", "payment_mobile_provider_id"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE contributions ADD COLUMN payment_mobile_provider_id INTEGER"))
            db.session.execute(
                text(
                    "ALTER TABLE contributions ADD CONSTRAINT fk_contrib_pmp "
                    "FOREIGN KEY (payment_mobile_provider_id) REFERENCES payment_mobile_providers(id) ON DELETE SET NULL"
                )
            )
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE contributions ADD payment_mobile_provider_id INT NULL"))
            db.session.execute(
                text(
                    "ALTER TABLE contributions ADD CONSTRAINT FK_contributions_pmp "
                    "FOREIGN KEY (payment_mobile_provider_id) REFERENCES payment_mobile_providers(id) ON DELETE SET NULL"
                )
            )
        else:
            db.session.execute(text("ALTER TABLE contributions ADD COLUMN payment_mobile_provider_id INTEGER"))
        try:
            db.session.execute(
                text("CREATE INDEX ix_contributions_payment_mobile_provider_id ON contributions (payment_mobile_provider_id)")
            )
        except Exception:
            pass
        db.session.commit()


def _ensure_member_documents_table(engine, dialect: str, _insp) -> None:
    """Create ``member_documents`` when migrations were not applied (PostgreSQL / SQL Server / SQLite)."""
    insp = inspect(engine)
    try:
        if insp.has_table("member_documents"):
            return
    except Exception:
        return
    if dialect == "postgresql":
        db.session.execute(
            text(
                """
                CREATE TABLE member_documents (
                    id SERIAL PRIMARY KEY,
                    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                    document_type VARCHAR(40) NOT NULL,
                    stored_path VARCHAR(500) NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    notes VARCHAR(500),
                    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    uploaded_by_user_id INTEGER REFERENCES app_users(id)
                )
                """
            )
        )
        db.session.execute(text("CREATE INDEX ix_member_documents_member_id ON member_documents (member_id)"))
    elif "mssql" in dialect:
        db.session.execute(
            text(
                """
                CREATE TABLE member_documents (
                    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    member_id INT NOT NULL,
                    document_type NVARCHAR(40) NOT NULL,
                    stored_path NVARCHAR(500) NOT NULL,
                    original_name NVARCHAR(255) NOT NULL,
                    notes NVARCHAR(500) NULL,
                    uploaded_at DATETIME2 NOT NULL CONSTRAINT DF_member_documents_uploaded_at DEFAULT SYSUTCDATETIME(),
                    uploaded_by_user_id INT NULL,
                    CONSTRAINT FK_member_documents_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
                    CONSTRAINT FK_member_documents_user FOREIGN KEY (uploaded_by_user_id) REFERENCES app_users(id)
                )
                """
            )
        )
        db.session.execute(text("CREATE INDEX ix_member_documents_member_id ON member_documents (member_id)"))
    else:
        db.session.execute(
            text(
                """
                CREATE TABLE member_documents (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                    document_type VARCHAR(40) NOT NULL,
                    stored_path VARCHAR(500) NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    notes VARCHAR(500),
                    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    uploaded_by_user_id INTEGER REFERENCES app_users(id)
                )
                """
            )
        )
        db.session.execute(text("CREATE INDEX ix_member_documents_member_id ON member_documents (member_id)"))
    db.session.commit()


def _ensure_finops_extensions_schema(engine, dialect: str) -> None:
    """Runtime safety net for payment controls, scheduling, and accounting close tables."""
    insp = inspect(engine)

    def _has_table(name: str) -> bool:
        try:
            return insp.has_table(name)
        except Exception:
            return False

    def _has_col(table: str, col: str) -> bool:
        try:
            return any(c.get("name") == col for c in insp.get_columns(table))
        except Exception:
            return False

    if _has_table("contributions"):
        if not _has_col("contributions", "reversal_of_id"):
            if dialect == "postgresql":
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversal_of_id INTEGER"))
            elif "mssql" in dialect:
                db.session.execute(text("ALTER TABLE contributions ADD reversal_of_id INT NULL"))
            else:
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversal_of_id INTEGER"))
        if not _has_col("contributions", "reversal_reason"):
            if dialect == "postgresql":
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversal_reason VARCHAR(500)"))
            elif "mssql" in dialect:
                db.session.execute(text("ALTER TABLE contributions ADD reversal_reason NVARCHAR(500) NULL"))
            else:
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversal_reason VARCHAR(500)"))
        if not _has_col("contributions", "reversed_at"):
            if dialect == "postgresql":
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversed_at TIMESTAMP"))
            elif "mssql" in dialect:
                db.session.execute(text("ALTER TABLE contributions ADD reversed_at DATETIME2 NULL"))
            else:
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversed_at TIMESTAMP"))
        if not _has_col("contributions", "reversed_by_user_id"):
            if dialect == "postgresql":
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversed_by_user_id INTEGER"))
            elif "mssql" in dialect:
                db.session.execute(text("ALTER TABLE contributions ADD reversed_by_user_id INT NULL"))
            else:
                db.session.execute(text("ALTER TABLE contributions ADD COLUMN reversed_by_user_id INTEGER"))
        try:
            db.session.execute(text("CREATE INDEX ix_contributions_reversal_of_id ON contributions (reversal_of_id)"))
        except Exception:
            pass
        db.session.commit()

    if not _has_table("subscription_amendments"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE subscription_amendments (
                        id SERIAL PRIMARY KEY,
                        subscription_id INTEGER NOT NULL REFERENCES share_subscriptions(id) ON DELETE CASCADE,
                        changed_by_user_id INTEGER REFERENCES app_users(id),
                        reason VARCHAR(500),
                        old_values_json TEXT NOT NULL,
                        new_values_json TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE subscription_amendments (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        subscription_id INT NOT NULL,
                        changed_by_user_id INT NULL,
                        reason NVARCHAR(500) NULL,
                        old_values_json NVARCHAR(MAX) NOT NULL,
                        new_values_json NVARCHAR(MAX) NOT NULL,
                        created_at DATETIME2 NOT NULL CONSTRAINT DF_sub_amd_created DEFAULT SYSUTCDATETIME(),
                        CONSTRAINT FK_sub_amd_sub FOREIGN KEY (subscription_id) REFERENCES share_subscriptions(id) ON DELETE CASCADE,
                        CONSTRAINT FK_sub_amd_user FOREIGN KEY (changed_by_user_id) REFERENCES app_users(id)
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE subscription_amendments (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        subscription_id INTEGER NOT NULL REFERENCES share_subscriptions(id) ON DELETE CASCADE,
                        changed_by_user_id INTEGER REFERENCES app_users(id),
                        reason VARCHAR(500),
                        old_values_json TEXT NOT NULL,
                        new_values_json TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_subscription_amendments_subscription_id ON subscription_amendments (subscription_id)"))
        db.session.commit()

    if not _has_table("accounting_period_closes"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE accounting_period_closes (
                        id SERIAL PRIMARY KEY,
                        close_date DATE NOT NULL UNIQUE,
                        notes VARCHAR(500),
                        closed_by_user_id INTEGER REFERENCES app_users(id),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE accounting_period_closes (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        close_date DATE NOT NULL UNIQUE,
                        notes NVARCHAR(500) NULL,
                        closed_by_user_id INT NULL,
                        created_at DATETIME2 NOT NULL CONSTRAINT DF_apc_created DEFAULT SYSUTCDATETIME(),
                        CONSTRAINT FK_apc_user FOREIGN KEY (closed_by_user_id) REFERENCES app_users(id)
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE accounting_period_closes (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        close_date DATE NOT NULL UNIQUE,
                        notes VARCHAR(500),
                        closed_by_user_id INTEGER REFERENCES app_users(id),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.commit()

    if not _has_table("report_schedules"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE report_schedules (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(120) NOT NULL,
                        report_key VARCHAR(64) NOT NULL,
                        frequency VARCHAR(20) NOT NULL DEFAULT 'weekly',
                        recipients TEXT NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        next_run_at TIMESTAMP NULL,
                        last_run_at TIMESTAMP NULL,
                        last_status VARCHAR(30),
                        last_error VARCHAR(500),
                        created_by_user_id INTEGER REFERENCES app_users(id),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE report_schedules (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        name NVARCHAR(120) NOT NULL,
                        report_key NVARCHAR(64) NOT NULL,
                        frequency NVARCHAR(20) NOT NULL CONSTRAINT DF_rs_freq DEFAULT 'weekly',
                        recipients NVARCHAR(MAX) NOT NULL,
                        is_active BIT NOT NULL CONSTRAINT DF_rs_active DEFAULT 1,
                        next_run_at DATETIME2 NULL,
                        last_run_at DATETIME2 NULL,
                        last_status NVARCHAR(30) NULL,
                        last_error NVARCHAR(500) NULL,
                        created_by_user_id INT NULL,
                        created_at DATETIME2 NOT NULL CONSTRAINT DF_rs_created DEFAULT SYSUTCDATETIME(),
                        CONSTRAINT FK_rs_user FOREIGN KEY (created_by_user_id) REFERENCES app_users(id)
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE report_schedules (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(120) NOT NULL,
                        report_key VARCHAR(64) NOT NULL,
                        frequency VARCHAR(20) NOT NULL DEFAULT 'weekly',
                        recipients TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        next_run_at TIMESTAMP NULL,
                        last_run_at TIMESTAMP NULL,
                        last_status VARCHAR(30),
                        last_error VARCHAR(500),
                        created_by_user_id INTEGER REFERENCES app_users(id),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_report_schedules_report_key ON report_schedules (report_key)"))
        db.session.commit()

    if not _has_table("notification_delivery_logs"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE notification_delivery_logs (
                        id SERIAL PRIMARY KEY,
                        channel VARCHAR(20) NOT NULL,
                        recipient VARCHAR(200) NOT NULL,
                        subject VARCHAR(200),
                        message_kind VARCHAR(40),
                        success BOOLEAN NOT NULL DEFAULT false,
                        attempt_count INTEGER NOT NULL DEFAULT 1,
                        error VARCHAR(500),
                        context_json TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE notification_delivery_logs (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        channel NVARCHAR(20) NOT NULL,
                        recipient NVARCHAR(200) NOT NULL,
                        subject NVARCHAR(200) NULL,
                        message_kind NVARCHAR(40) NULL,
                        success BIT NOT NULL CONSTRAINT DF_ndl_success DEFAULT 0,
                        attempt_count INT NOT NULL CONSTRAINT DF_ndl_attempt DEFAULT 1,
                        error NVARCHAR(500) NULL,
                        context_json NVARCHAR(MAX) NULL,
                        created_at DATETIME2 NOT NULL CONSTRAINT DF_ndl_created DEFAULT SYSUTCDATETIME()
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE notification_delivery_logs (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        channel VARCHAR(20) NOT NULL,
                        recipient VARCHAR(200) NOT NULL,
                        subject VARCHAR(200),
                        message_kind VARCHAR(40),
                        success INTEGER NOT NULL DEFAULT 0,
                        attempt_count INTEGER NOT NULL DEFAULT 1,
                        error VARCHAR(500),
                        context_json TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_notification_delivery_logs_recipient ON notification_delivery_logs (recipient)"))
        db.session.commit()

    if not _has_table("agent_country_regions"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE agent_country_regions (
                        id SERIAL PRIMARY KEY,
                        country_name VARCHAR(120) NOT NULL,
                        region_name VARCHAR(200) NOT NULL,
                        source VARCHAR(20) NOT NULL DEFAULT 'api',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_agent_country_regions_c_r UNIQUE (country_name, region_name)
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE agent_country_regions (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        country_name NVARCHAR(120) NOT NULL,
                        region_name NVARCHAR(200) NOT NULL,
                        source NVARCHAR(20) NOT NULL CONSTRAINT DF_acr_source DEFAULT 'api',
                        created_at DATETIME2 NOT NULL CONSTRAINT DF_acr_created DEFAULT SYSUTCDATETIME(),
                        CONSTRAINT uq_agent_country_regions_c_r UNIQUE (country_name, region_name)
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE agent_country_regions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        country_name VARCHAR(120) NOT NULL,
                        region_name VARCHAR(200) NOT NULL,
                        source VARCHAR(20) NOT NULL DEFAULT 'api',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_agent_country_regions_c_r UNIQUE (country_name, region_name)
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_agent_country_regions_country_name ON agent_country_regions (country_name)"))
        db.session.commit()


def _ensure_rbac_schema(engine, dialect: str, insp) -> None:
    """Permission catalog, role defaults, per-user grants, and ``is_superuser`` for full override."""

    def _has_table(name: str) -> bool:
        try:
            return insp.has_table(name)
        except Exception:
            return False

    def _has_col(table: str, col: str) -> bool:
        try:
            return any(c.get("name") == col for c in insp.get_columns(table))
        except Exception:
            return False

    if _has_table("app_users") and not _has_col("app_users", "is_superuser"):
        if dialect == "postgresql":
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN is_superuser BOOLEAN NOT NULL DEFAULT false"))
        elif "mssql" in dialect:
            db.session.execute(text("ALTER TABLE app_users ADD is_superuser BIT NOT NULL CONSTRAINT DF_app_users_su DEFAULT 0"))
        else:
            db.session.execute(text("ALTER TABLE app_users ADD COLUMN is_superuser INTEGER NOT NULL DEFAULT 0"))
        db.session.commit()
        try:
            db.session.execute(text("UPDATE app_users SET is_superuser = 1 WHERE role = 'admin' OR role = 'administrator'"))
        except Exception:
            db.session.execute(
                text("UPDATE app_users SET is_superuser = 1 WHERE role = 'admin'")
            )  # sqlite
        try:
            db.session.execute(
                text("UPDATE app_users SET is_superuser = 1 WHERE LOWER(role) = 'admin'")
            )
        except Exception:
            pass
        db.session.commit()
        insp = inspect(engine)

    if not _has_table("permission_definitions"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE permission_definitions (
                        id SERIAL PRIMARY KEY,
                        key VARCHAR(100) NOT NULL UNIQUE,
                        label VARCHAR(200) NOT NULL,
                        description TEXT,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE permission_definitions (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        key NVARCHAR(100) NOT NULL UNIQUE,
                        label NVARCHAR(200) NOT NULL,
                        description NVARCHAR(MAX) NULL,
                        sort_order INT NOT NULL CONSTRAINT DF_pd_sort DEFAULT 0,
                        is_active BIT NOT NULL CONSTRAINT DF_pd_active DEFAULT 1,
                        created_at DATETIME2 NOT NULL CONSTRAINT DF_pd_created DEFAULT SYSUTCDATETIME()
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE permission_definitions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        key VARCHAR(100) NOT NULL UNIQUE,
                        label VARCHAR(200) NOT NULL,
                        description TEXT,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_pd_key ON permission_definitions (key)"))
        db.session.commit()

    if not _has_table("role_default_permissions"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE role_default_permissions (
                        id SERIAL PRIMARY KEY,
                        role VARCHAR(32) NOT NULL,
                        permission_id INTEGER NOT NULL REFERENCES permission_definitions(id) ON DELETE CASCADE,
                        CONSTRAINT uq_rdp_role_perm UNIQUE (role, permission_id)
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE role_default_permissions (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        role NVARCHAR(32) NOT NULL,
                        permission_id INT NOT NULL,
                        CONSTRAINT uq_rdp_role_perm UNIQUE (role, permission_id),
                        CONSTRAINT FK_rdp_pd FOREIGN KEY (permission_id) REFERENCES permission_definitions(id) ON DELETE CASCADE
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE role_default_permissions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        role VARCHAR(32) NOT NULL,
                        permission_id INTEGER NOT NULL REFERENCES permission_definitions(id) ON DELETE CASCADE,
                        CONSTRAINT uq_rdp_role_perm UNIQUE (role, permission_id)
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_rdp_role ON role_default_permissions (role)"))
        db.session.commit()

    if not _has_table("user_granted_permissions"):
        if dialect == "postgresql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_granted_permissions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                        permission_id INTEGER NOT NULL REFERENCES permission_definitions(id) ON DELETE CASCADE,
                        CONSTRAINT uq_ugp_user_perm UNIQUE (user_id, permission_id)
                    )
                    """
                )
            )
        elif "mssql" in dialect:
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_granted_permissions (
                        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        user_id INT NOT NULL,
                        permission_id INT NOT NULL,
                        CONSTRAINT uq_ugp_user_perm UNIQUE (user_id, permission_id),
                        CONSTRAINT FK_ugp_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
                        CONSTRAINT FK_ugp_pd FOREIGN KEY (permission_id) REFERENCES permission_definitions(id) ON DELETE CASCADE
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_granted_permissions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                        permission_id INTEGER NOT NULL REFERENCES permission_definitions(id) ON DELETE CASCADE,
                        CONSTRAINT uq_ugp_user_perm UNIQUE (user_id, permission_id)
                    )
                    """
                )
            )
        db.session.execute(text("CREATE INDEX ix_ugp_user_id ON user_granted_permissions (user_id)"))
        db.session.commit()

    from estithmar.rbac import ensure_rbac_seed

    try:
        ensure_rbac_seed()
    except Exception:
        db.session.rollback()
