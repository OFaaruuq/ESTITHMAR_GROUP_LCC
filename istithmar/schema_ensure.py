"""Add columns introduced after first deploy (when migrations are not run)."""

from __future__ import annotations

from sqlalchemy import inspect, text

from istithmar import db


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
