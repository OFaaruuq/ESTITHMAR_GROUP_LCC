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
