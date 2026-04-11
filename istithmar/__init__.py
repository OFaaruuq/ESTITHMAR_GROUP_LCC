import os

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import DBAPIError

from istithmar.config import PROJECT_ROOT, get_database_uri, resolve_static_folder


def _reraise_if_sql_login_failed(exc: BaseException) -> None:
    """Attach a short hint for SQL Server error 18456 (invalid SQL login)."""
    raw = str(getattr(exc, "orig", exc))
    if "18456" not in raw and "login failed" not in raw.lower():
        return
    raise RuntimeError(
        "SQL Server rejected the login (error 18456). Options: "
        "(1) Create a SQL login in SSMS with the same name/password as DB_USER/DB_PASSWORD, "
        "enable Mixed Mode authentication, and grant access to DB_NAME; "
        "(2) Or set ISTITHMAR_MSSQL_USE_WINDOWS_AUTH=yes (and remove or ignore DB_USER/DB_PASSWORD) "
        "to use your Windows account; "
        "(3) If the password contains @ or ?, wrap it in double quotes in .env, e.g. DB_PASSWORD=\"...\"."
    ) from exc

db = SQLAlchemy()
migrate = Migrate()


def create_app(config=None):
    """
    Application factory. Expects current working directory to be
    ``Admin/istithmar_app`` when using ``flask run`` or ``python run.py``.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(PROJECT_ROOT, ".flaskenv"))
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    except ImportError:
        pass

    static_root = resolve_static_folder()

    app = Flask(
        __name__,
        template_folder=os.path.join(PROJECT_ROOT, "templates"),
        static_folder=static_root,
        static_url_path="",
    )
    app.config["SECRET_KEY"] = os.environ.get(
        "ISTITHMAR_SECRET_KEY", "istithmar-dev-change-in-production"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if config:
        app.config.update(config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()

    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"pool_pre_ping": True})

    db.init_app(app)
    migrate.init_app(app, db)

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

    try:
        with app.app_context():
            from istithmar import models  # noqa: F401
            import istithmar.accounting_models  # noqa: F401  — GL tables

            if app.config.get("TESTING"):
                db.create_all()
            else:
                from flask_migrate import upgrade as flask_migrate_upgrade

                migrations_env = os.path.join(PROJECT_ROOT, "migrations", "env.py")
                if os.path.isfile(migrations_env):
                    try:
                        flask_migrate_upgrade()
                    except Exception:
                        db.create_all()
                else:
                    db.create_all()

            from sqlalchemy import or_

            from istithmar.models import Investment, Project, next_investment_code, next_project_code

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

            from istithmar.auth import init_auth, seed_if_empty
            from istithmar.schema_ensure import ensure_app_schema

            ensure_app_schema()

            init_auth(app)
            seed_if_empty()
    except DBAPIError as e:
        _reraise_if_sql_login_failed(e)
        raise

    from istithmar.routes import register_routes

    register_routes(app)

    return app
