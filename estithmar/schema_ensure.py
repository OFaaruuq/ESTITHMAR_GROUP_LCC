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
    _ensure_payment_options_schema(engine, dialect)


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
