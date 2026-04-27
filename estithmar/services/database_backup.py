"""On-demand database backup for administrators (MSSQL backup file or PostgreSQL ``pg_dump``)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from sqlalchemy.engine import make_url

from estithmar.config import PROJECT_ROOT


def default_data_backup_root() -> str:
    return os.path.join(PROJECT_ROOT, "data", "backups")


def resolve_backup_subdir(subfolder: str) -> str:
    """Return an absolute path under ``data/backups``; ``subfolder`` is a single segment (e.g. ``monthly``)."""
    root = os.path.abspath(default_data_backup_root())
    s = (subfolder or "").strip()
    if not s:
        os.makedirs(root, exist_ok=True)
        return root
    if ".." in s or os.path.isabs(s) or "/" in s or "\\" in s or ":" in s:
        raise ValueError("Subfolder must be a single name, not a path (use only letters, numbers, spaces, dashes).")
    if not re.match(r"^[\w.\-()@ ]{1,120}$", s):
        raise ValueError("Invalid subfolder name.")
    out = os.path.abspath(os.path.join(root, s))
    if not (out == root or out.startswith(root + os.sep)):
        raise ValueError("Backup path is outside the allowed data backups area.")
    os.makedirs(out, exist_ok=True)
    return out


def get_engine_dialect_name(app) -> str | None:
    try:
        e = app.extensions["sqlalchemy"].db.engine
        if e is None:
            return None
        return e.dialect.name
    except Exception:
        return None


def parse_database_name_from_uri(uri: str) -> str:
    u = make_url(uri)
    d = (u.database or "").strip()
    if not d:
        raise ValueError("Database name is empty in the connection string.")
    return d


def _mssql_bracket_id(name: str) -> str:
    if ";" in name or "\x00" in name or len(name) > 256:
        raise ValueError("Invalid database name for backup.")
    return name.replace("]", "]]")


def is_safe_file_segment(name: str) -> str:
    s = (name or "").strip()
    if not s or ".." in s or "/" in s or "\\" in s or ":" in s:
        raise ValueError("Use a simple file name (no path separators or :).")
    if not re.match(r"^[\w.\-()@ ]{1,200}$", s):
        raise ValueError("The file name contains disallowed characters.")
    return s


def resolve_backup_file_path(backup_dir: str, file_name: str) -> str:
    root = os.path.abspath(os.path.normpath(backup_dir))
    seg = is_safe_file_segment(file_name)
    low = seg.lower()
    if not (low.endswith(".bak") or low.endswith(".sql") or low.endswith(".dump")):
        raise ValueError("File name must end with .bak, .sql, or .dump.")
    os.makedirs(root, exist_ok=True)
    out_abs = os.path.abspath(os.path.join(root, seg))
    if not (out_abs == root or out_abs.startswith(root + os.sep)):
        raise ValueError("Resolved path is outside the backup folder.")
    return out_abs


def run_mssql_full_backup(backup_bak_path: str, *, copy_only: bool) -> str:
    from estithmar import db

    eng = db.engine
    dname = (eng.dialect.name or "").lower()
    if dname not in ("mssql",) and "mssql" not in str(eng.url).lower():
        raise RuntimeError("Current engine is not Microsoft SQL Server (mssql+pyodbc).")

    dbname = parse_database_name_from_uri(str(eng.url))
    p = os.path.normpath(backup_bak_path).replace("'", "''")
    bname = _mssql_bracket_id(dbname)
    with_parts = ["FORMAT", "INIT"]
    if copy_only:
        with_parts.append("COPY_ONLY")
    sql = f"BACKUP DATABASE [{bname}] TO DISK = N'{p}' WITH {', '.join(with_parts)}, STATS = 5"
    con = eng.raw_connection()
    try:
        con.autocommit = True
        cur = con.cursor()
        cur.execute(sql)
    finally:
        con.close()
    return f"SQL Server wrote: {backup_bak_path}"


def run_postgres_custom_backup(out_path: str, *, use_custom: bool, uri: str) -> str:
    """``pg_dump``; ``use_custom`` → custom binary ``.dump``; else plain ``.sql`` file."""
    u = make_url(uri)
    s = str(u)
    if "postgre" not in s.lower() and "psycopg" not in s.lower():
        raise RuntimeError("Not a PostgreSQL connection string.")
    if not shutil.which("pg_dump"):
        raise RuntimeError("pg_dump was not found on PATH. Install PostgreSQL client tools on the app server.")
    if not u.username:
        raise ValueError("DB user in URI is required for pg_dump.")
    user = unquote(str(u.username))
    host = (u.host or "127.0.0.1") or "127.0.0.1"
    port = u.port or 5432
    database = (u.database or "postgres").strip() or "postgres"
    env = os.environ.copy()
    if u.password is not None:
        env["PGPASSWORD"] = unquote(str(u.password))
    if use_custom:
        cmd: list[str] = [
            "pg_dump", "-h", str(host), "-p", str(port), "-U", str(user), "-d", database,
            "-F", "c", "-f", out_path, "--no-password",
        ]
    else:
        cmd = [
            "pg_dump", "-h", str(host), "-p", str(port), "-U", str(user), "-d", database,
            "-F", "p", "-f", out_path, "--no-password",
        ]
    p = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=7200,
    )
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip() or f"exit {p.returncode}"
        raise RuntimeError(f"pg_dump failed: {err[:2000]}")

    return f"pg_dump created: {out_path}"


def list_backup_dir(backup_dir: str, limit: int = 40) -> list[dict[str, Any]]:
    if not os.path.isdir(backup_dir):
        return []
    rows: list[dict[str, Any]] = []
    try:
        for n in os.listdir(backup_dir):
            full = os.path.join(backup_dir, n)
            if not os.path.isfile(full):
                continue
            st = os.stat(full)
            rows.append({"name": n, "size": st.st_size, "modified": st.st_mtime})
    except OSError:
        return []
    rows.sort(key=lambda r: r.get("modified") or 0, reverse=True)
    return rows[:limit]


def suggested_mssql_bak_name() -> str:
    return "estithmar_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak"


def suggested_pg_dump_name(custom: bool) -> str:
    s = "estithmar_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    return s + (".dump" if custom else ".sql")
