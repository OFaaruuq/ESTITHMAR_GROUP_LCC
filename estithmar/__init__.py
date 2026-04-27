import os
import re
import sys

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import DBAPIError

from estithmar.config import (
    PROJECT_ROOT,
    get_database_uri,
    promote_legacy_env_vars_to_estithmar,
    resolve_static_folder,
)


def _reraise_if_sql_login_failed(exc: BaseException) -> None:
    """Attach a short hint for SQL Server error 18456 (invalid SQL login)."""
    raw = str(getattr(exc, "orig", exc))
    if "18456" not in raw and "login failed" not in raw.lower():
        return
    raise RuntimeError(
        "SQL Server rejected the login (error 18456). Options: "
        "(1) Create a SQL login in SSMS with the same name/password as DB_USER/DB_PASSWORD, "
        "enable Mixed Mode authentication, and grant access to DB_NAME; "
        "(2) Or set ESTITHMAR_MSSQL_USE_WINDOWS_AUTH=yes (and remove or ignore DB_USER/DB_PASSWORD) "
        "to use your Windows account; "
        "(3) If the password contains @ or ?, wrap it in double quotes in .env, e.g. DB_PASSWORD=\"...\"."
    ) from exc

db = SQLAlchemy()
migrate = Migrate()


def _should_run_startup_migrate() -> bool:
    """Run Alembic + schema repair on normal app startup; skip for ``flask db …`` / ``prepare-*`` CLIs."""
    if os.environ.get("ESTITHMAR_SKIP_STARTUP_MIGRATE", "").lower() in ("1", "true", "yes", "on"):
        return False
    joined = " ".join(sys.argv).lower()
    if "prepare-mssql-legacy-fks" in joined:
        return False
    if re.search(r"\bflask\s+db\b", joined) or re.search(r"-m\s+flask\s+db\b", joined):
        return False
    return True


def _should_auto_mssql_prepare_before_migrate() -> bool:
    """MSSQL FK/default prep before Alembic (idempotent; no row deletes). Disable with env if needed."""
    if os.environ.get("ESTITHMAR_SKIP_MSSQL_PREPARE_ON_STARTUP", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    return _should_run_startup_migrate()


def create_app(config=None):
    """
    Application factory. Expects current working directory to be
    ``Admin/estithmar_app`` when using ``flask run`` or ``python run.py``.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(PROJECT_ROOT, ".flaskenv"))
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    except ImportError:
        pass

    promote_legacy_env_vars_to_estithmar()

    static_root = resolve_static_folder()

    app = Flask(
        __name__,
        template_folder=os.path.join(PROJECT_ROOT, "templates"),
        static_folder=static_root,
        static_url_path="",
    )
    app.config["SECRET_KEY"] = os.environ.get(
        "ESTITHMAR_SECRET_KEY", "estithmar-dev-change-in-production"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if config:
        app.config.update(config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()

    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"pool_pre_ping": True})

    db.init_app(app)
    migrate.init_app(app, db)

    @app.cli.command("prepare-mssql-legacy-fks")
    def prepare_mssql_legacy_fks():
        """Optional MSSQL repair: legacy invoice FKs + ``DF_*`` before migrate (MSSQL 3726/5074).

        The same logic runs **automatically** before ``flask_migrate_upgrade()`` on normal app
        startup (``flask run``, gunicorn, etc.) when ``ESTITHMAR_SKIP_MSSQL_PREPARE_ON_STARTUP`` is
        not set. Use this command for troubleshooting or if startup migrate is disabled.

        Does not ``DROP TABLE`` or delete rows. Safe to repeat.
        """
        from estithmar.mssql_alembic import prepare_mssql_legacy_invoice_fks

        print("prepare-mssql-legacy-fks: running…", flush=True)
        dialect = (db.engine.dialect.name or "").lower() if db.engine else ""
        if dialect and "mssql" not in dialect:
            print("This command is only needed on Microsoft SQL Server (mssql).")
            return
        out = prepare_mssql_legacy_invoice_fks(db.engine)
        if out.get("skipped"):
            print("Not an MSSQL database; nothing to do.")
            return
        print(
            "Dropped "
            f"{out.get('parent_to_invoices', 0)} FK(s) from contributions→invoices, "
            f"{out.get('from_referenced', 0)} FK(s) by referenced table (invoices/invoice_lines), "
            f"{out.get('known_named', 0)} by known name (e.g. FK_contributions_invoice), "
            f"{out.get('defaults_for_alter', 0)} default constraint(s) that block DATETIME2 alters. "
            "On production, the same prep runs automatically before migrate on app startup; "
            "or run: flask db upgrade"
        )

    @app.template_filter("money")
    def money_fmt(v):
        from decimal import Decimal

        if v is None:
            return "0.00"
        try:
            d = Decimal(str(v))
            return f"{d:,.2f}"
        except Exception:
            return str(v)

    @app.template_filter("payment_type_label")
    def payment_type_label(v):
        """Map stored contribution.payment_type to business-document labels."""
        if not v:
            return "—"
        key = str(v).strip()
        return {
            "Cash": "Cash",
            "Mobile": "Mobile money",
            "Bank": "Bank transfer",
            "Other": "Other",
        }.get(key, key)

    @app.template_filter("member_public_id")
    def member_public_id_filter(v):
        """Format a stored member public code (``IST-*`` → ``EST-*`` for display)."""
        from estithmar.models import format_member_public_id

        return format_member_public_id(v)

    try:
        with app.app_context():
            from estithmar import models  # noqa: F401
            import estithmar.accounting_models  # noqa: F401  — GL tables

            if app.config.get("TESTING"):
                db.create_all()
            elif _should_run_startup_migrate():
                # Normal ``flask run`` / production worker: MSSQL prep (idempotent), migrate, seed.
                # Skipped for ``flask db …`` / ``prepare-mssql-legacy-fks`` so those CLIs are not blocked
                # by duplicate migrate or long-running seed before the command body runs.
                from flask_migrate import upgrade as flask_migrate_upgrade

                migrations_env = os.path.join(PROJECT_ROOT, "migrations", "env.py")
                if os.path.isfile(migrations_env):
                    try:
                        if _should_auto_mssql_prepare_before_migrate() and (
                            "mssql" in (db.engine.dialect.name or "").lower()
                        ):
                            from estithmar.mssql_alembic import prepare_mssql_legacy_invoice_fks

                            prepare_mssql_legacy_invoice_fks(db.engine)
                        flask_migrate_upgrade()
                    except Exception:
                        db.create_all()
                elif not os.path.isfile(migrations_env):
                    db.create_all()

                from sqlalchemy import or_

                from estithmar.models import Investment, Project, next_investment_code, next_project_code

                for p in (
                    Project.query.filter(or_(Project.project_code.is_(None), Project.project_code == ""))
                    .order_by(Project.id)
                    .all()
                ):
                    p.project_code = next_project_code()
                for inv in (
                    Investment.query.filter(
                        or_(Investment.investment_code.is_(None), Investment.investment_code == "")
                    )
                    .order_by(Investment.id)
                    .all()
                ):
                    inv.investment_code = next_investment_code()
                db.session.commit()

                from estithmar.auth import init_auth, seed_if_empty
                from estithmar.schema_ensure import ensure_app_schema

                ensure_app_schema()

                init_auth(app)
                seed_if_empty()
    except DBAPIError as e:
        _reraise_if_sql_login_failed(e)
        raise

    from estithmar.routes import register_routes

    register_routes(app)

    return app
