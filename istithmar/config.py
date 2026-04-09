"""
Path layout (run all commands from the project root: Admin/istithmar_app).

  istithmar_app/          <- PROJECT_ROOT (venv, app.py, templates/)
    istithmar/            <- Python package
    templates/
    static/               <- optional: copy Admin/dist/assets -> static/assets
  ../dist/                <- default theme assets (Admin/dist/assets/...)
"""
import os
from urllib.parse import quote_plus

# Directory containing this file: .../istithmar_app/istithmar/
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# Project root: .../istithmar_app  (where venv, app.py, templates live)
PROJECT_ROOT = os.path.abspath(os.path.join(_PACKAGE_DIR, ".."))

# Tocly template build output next to istithmar_app
DIST_DIR = os.path.join(PROJECT_ROOT, "..", "dist")
# Optional self-contained copy inside the app folder
LOCAL_STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

ISTITHMAR_ENV_STAGING = "staging"
ISTITHMAR_ENV_PRODUCTION = "production"
ISTITHMAR_ENV_DEVELOPMENT = "development"


class DatabaseConfigurationError(RuntimeError):
    """Missing or invalid database URL for the current ISTITHMAR_ENV."""


def _normalize_postgres_url(uri: str) -> str:
    uri = uri.strip()
    if uri.startswith("postgres://"):
        uri = "postgresql://" + uri[len("postgres://") :]
    return uri


def _is_postgresql_uri(uri: str) -> bool:
    return uri.strip().lower().startswith("postgresql")


def _is_mssql_uri(uri: str) -> bool:
    return "mssql" in uri.strip().lower()


def _is_loopback_sql_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1")


def _postgres_uri_from_components(
    user: str,
    password: str,
    host: str,
    port: str,
    database: str,
) -> str:
    """Build a SQLAlchemy PostgreSQL URI; encodes user/password (e.g. ``@`` in password)."""
    u = quote_plus(user, safe="")
    p = quote_plus(password, safe="")
    return f"postgresql+psycopg2://{u}:{p}@{host}:{port}/{database}"


def _env_flag_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes")


def _mssql_odbc_query_params(host: str, *, trusted_connection: bool) -> str:
    """Query string for ``mssql+pyodbc`` (after ``?``): driver, optional Windows auth, encrypt, trust."""
    driver = os.environ.get("ISTITHMAR_MSSQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    driver_q = quote_plus(driver, safe="")
    parts = [f"driver={driver_q}"]
    if trusted_connection:
        parts.append("Trusted_Connection=yes")
    encrypt = os.environ.get("ISTITHMAR_MSSQL_ENCRYPT", "yes")
    parts.append(f"Encrypt={quote_plus(encrypt, safe='')}")
    tsc_raw = os.environ.get("ISTITHMAR_MSSQL_TRUST_SERVER_CERTIFICATE")
    tsc = (tsc_raw or "").strip().lower()
    trust = False
    if tsc in ("0", "false", "no"):
        trust = False
    elif tsc in ("1", "true", "yes"):
        trust = True
    elif tsc_raw is None or tsc == "":
        trust = _is_loopback_sql_host(host)
    if trust:
        parts.append("TrustServerCertificate=yes")
    return "&".join(parts)


def _mssql_uri_from_db_components(
    user: str,
    password: str,
    host: str,
    port: str,
    database: str,
) -> str:
    """Build SQLAlchemy pyodbc URI for Microsoft SQL Server (password URL-encoded)."""
    u = quote_plus(user, safe="")
    p = quote_plus(password, safe="")
    q = _mssql_odbc_query_params(host, trusted_connection=False)
    return f"mssql+pyodbc://{u}:{p}@{host}:{port}/{database}?{q}"


def _mssql_uri_trusted_connection(host: str, port: str, database: str) -> str:
    """SQL Server integrated / Windows authentication (no DB_USER / DB_PASSWORD)."""
    q = _mssql_odbc_query_params(host, trusted_connection=True)
    return f"mssql+pyodbc://@{host}:{port}/{database}?{q}"


def _try_mssql_uri_from_db_env_vars() -> str | None:
    """
    Build MSSQL URI from ``DB_*``:

    - **SQL authentication** (default): ``DB_USER``, ``DB_PASSWORD``, ``DB_NAME``, ``DB_HOST``;
      optional ``DB_PORT`` (default ``1433``).
    - **Windows authentication**: set ``ISTITHMAR_MSSQL_USE_WINDOWS_AUTH=yes`` (or ``DB_USE_WINDOWS_AUTH=yes``);
      then only ``DB_NAME``, ``DB_HOST``, optional ``DB_PORT`` are required.

    Tuning: ``ISTITHMAR_MSSQL_ODBC_DRIVER``, ``ISTITHMAR_MSSQL_ENCRYPT``,
    ``ISTITHMAR_MSSQL_TRUST_SERVER_CERTIFICATE``.
    """
    database = os.environ.get("DB_NAME")
    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT") or "1433"
    if not database or not host:
        return None
    if _env_flag_true("ISTITHMAR_MSSQL_USE_WINDOWS_AUTH") or _env_flag_true("DB_USE_WINDOWS_AUTH"):
        return _mssql_uri_trusted_connection(host, str(port), database)
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    if not user or password is None:
        return None
    return _mssql_uri_from_db_components(user, password, host, str(port), database)


def _try_postgres_uri_from_env_vars() -> str | None:
    """
    If ``ISTITHMAR_PG_USER`` / ``ISTITHMAR_PG_PASSWORD`` / ``ISTITHMAR_PG_DATABASE`` are set
    (or ``POSTGRES_USER`` / ``POSTGRES_PASSWORD`` / ``POSTGRES_DB``), build the URI.

    Optional: ``ISTITHMAR_PG_HOST`` (default ``127.0.0.1``), ``ISTITHMAR_PG_PORT`` (default ``5432``).
    """
    user = os.environ.get("ISTITHMAR_PG_USER") or os.environ.get("POSTGRES_USER")
    password = os.environ.get("ISTITHMAR_PG_PASSWORD")
    if password is None:
        password = os.environ.get("POSTGRES_PASSWORD")
    database = os.environ.get("ISTITHMAR_PG_DATABASE") or os.environ.get("POSTGRES_DB")
    if not user or password is None or not database:
        return None
    host = os.environ.get("ISTITHMAR_PG_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("ISTITHMAR_PG_PORT") or os.environ.get("POSTGRES_PORT") or "5432"
    return _postgres_uri_from_components(user, password, host, str(port), database)


def get_istithmar_env() -> str:
    """Return ``staging``, ``production``, or ``development`` (default)."""
    v = (os.environ.get("ISTITHMAR_ENV") or ISTITHMAR_ENV_DEVELOPMENT).strip().lower()
    if v in (ISTITHMAR_ENV_STAGING, ISTITHMAR_ENV_PRODUCTION, ISTITHMAR_ENV_DEVELOPMENT):
        return v
    return ISTITHMAR_ENV_DEVELOPMENT


def get_database_uri() -> str:
    """
    SQLAlchemy database URI (mixed support in development, strict by environment elsewhere).

    Resolution order:

    1. ``ISTITHMAR_DATABASE_URL`` or ``DATABASE_URL`` (first non-empty wins).
    2. Else, from ``ISTITHMAR_ENV`` (default ``development``):

       - ``staging`` → ``ISTITHMAR_STAGING_DATABASE_URL``
       - ``production`` → ``ISTITHMAR_PRODUCTION_DATABASE_URL``
       - ``development`` → ``ISTITHMAR_DEVELOPMENT_DATABASE_URL``

    3. Else, fallback component variables:

       - PostgreSQL: ``ISTITHMAR_PG_*`` (or ``POSTGRES_*``)
       - SQL Server: ``DB_*`` (and optional MSSQL tuning flags)

    **Staging (PostgreSQL)**::

        postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE

    **Production (Microsoft SQL Server)**::

        mssql+pyodbc://USER:PASSWORD@HOST:1433/DATABASE?driver=ODBC+Driver+18+for+SQL+Server

    Heroku-style ``postgres://`` is normalized to ``postgresql://``.
    URL-encode special characters in passwords.

    **Development (flexible)**::

        postgresql+psycopg2://...  OR  mssql+pyodbc://...

    Raises ``DatabaseConfigurationError`` if no URI is configured, or if the URI
    does not match the expected backend policy for ``ISTITHMAR_ENV``.
    """
    uri = os.environ.get("ISTITHMAR_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not (uri and uri.strip()):
        env = get_istithmar_env()
        if env == ISTITHMAR_ENV_STAGING:
            uri = os.environ.get("ISTITHMAR_STAGING_DATABASE_URL")
        elif env == ISTITHMAR_ENV_PRODUCTION:
            uri = os.environ.get("ISTITHMAR_PRODUCTION_DATABASE_URL")
        else:
            uri = os.environ.get("ISTITHMAR_DEVELOPMENT_DATABASE_URL")

    if not (uri and str(uri).strip()):
        env = get_istithmar_env()
        if env == ISTITHMAR_ENV_STAGING:
            uri = _try_postgres_uri_from_env_vars()
        elif env == ISTITHMAR_ENV_PRODUCTION:
            uri = _try_mssql_uri_from_db_env_vars()
        else:
            # Development accepts either backend. Prefer explicit PostgreSQL vars first
            # for backward compatibility, then SQL Server DB_* vars.
            uri = _try_postgres_uri_from_env_vars() or _try_mssql_uri_from_db_env_vars()

    if not uri or not str(uri).strip():
        raise DatabaseConfigurationError(
            "Database URL is required. Set ISTITHMAR_DATABASE_URL or "
            "DATABASE_URL, or set ISTITHMAR_STAGING_DATABASE_URL / ISTITHMAR_PRODUCTION_DATABASE_URL / "
            "ISTITHMAR_DEVELOPMENT_DATABASE_URL to match ISTITHMAR_ENV, or set ISTITHMAR_PG_USER / "
            "ISTITHMAR_PG_PASSWORD / ISTITHMAR_PG_DATABASE (and optional host/port). "
            "For SQL Server with ISTITHMAR_ENV=production, set ISTITHMAR_PRODUCTION_DATABASE_URL "
            "or DB_HOST / DB_NAME (and optional DB_PORT), plus either DB_USER / DB_PASSWORD "
            "or ISTITHMAR_MSSQL_USE_WINDOWS_AUTH=yes for Windows authentication."
        )

    uri = _normalize_postgres_url(str(uri))
    env = get_istithmar_env()

    if env == ISTITHMAR_ENV_PRODUCTION:
        if not _is_mssql_uri(uri):
            raise DatabaseConfigurationError(
                "ISTITHMAR_ENV=production requires a Microsoft SQL Server URI "
                "(e.g. mssql+pyodbc://...)."
            )
    elif env == ISTITHMAR_ENV_STAGING:
        if not _is_postgresql_uri(uri):
            raise DatabaseConfigurationError(
                "ISTITHMAR_ENV=staging requires PostgreSQL "
                "(e.g. postgresql+psycopg2://...), not this URI."
            )
    else:
        if not (_is_postgresql_uri(uri) or _is_mssql_uri(uri)):
            raise DatabaseConfigurationError(
                "ISTITHMAR_ENV=development requires either PostgreSQL "
                "(postgresql+psycopg2://...) or SQL Server (mssql+pyodbc://...)."
            )

    return uri


def get_test_database_uri() -> str:
    """
    PostgreSQL URI for automated tests (pytest).

    Set ``ISTITHMAR_TEST_DATABASE_URL`` to a full URI, or set ``ISTITHMAR_PG_USER`` /
    ``ISTITHMAR_PG_PASSWORD`` (and optional host/port). Database name: prefer
    ``ISTITHMAR_PG_TEST_DATABASE``; if unset, use ``ISTITHMAR_PG_DATABASE`` / ``POSTGRES_DB``
    so tests can share the dev database; otherwise default ``estithmar_test``.
    """
    explicit = os.environ.get("ISTITHMAR_TEST_DATABASE_URL")
    if explicit and explicit.strip():
        return _normalize_postgres_url(explicit.strip())
    user = os.environ.get("ISTITHMAR_PG_USER") or os.environ.get("POSTGRES_USER")
    password = os.environ.get("ISTITHMAR_PG_PASSWORD")
    if password is None:
        password = os.environ.get("POSTGRES_PASSWORD")
    database = os.environ.get("ISTITHMAR_PG_TEST_DATABASE")
    if not database:
        database = (
            os.environ.get("ISTITHMAR_PG_DATABASE")
            or os.environ.get("POSTGRES_DB")
            or "estithmar_test"
        )
    if not user or password is None:
        raise DatabaseConfigurationError(
            "Tests require PostgreSQL. Set ISTITHMAR_TEST_DATABASE_URL or "
            "ISTITHMAR_PG_USER and ISTITHMAR_PG_PASSWORD (and optional ISTITHMAR_PG_TEST_DATABASE)."
        )
    host = os.environ.get("ISTITHMAR_PG_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("ISTITHMAR_PG_PORT") or os.environ.get("POSTGRES_PORT") or "5432"
    return _postgres_uri_from_components(user, password, host, str(port), database)


def resolve_static_folder():
    """
    Serve CSS/JS/images from the same paths templates expect: /assets/...

    Priority:
    1) ../dist  if it contains assets/ (normal layout: Admin/dist + Admin/istithmar_app)
    2) static/  if it contains assets/ (after copying dist/assets into istithmar_app/static/assets)
    3) ../dist  anyway (may 404 until theme files are present)
    """
    if os.path.isdir(os.path.join(DIST_DIR, "assets")):
        return DIST_DIR
    if os.path.isdir(os.path.join(LOCAL_STATIC_DIR, "assets")):
        return LOCAL_STATIC_DIR
    return DIST_DIR
