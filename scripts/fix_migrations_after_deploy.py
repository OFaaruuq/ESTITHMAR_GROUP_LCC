"""
Auto-fix known Alembic migration issues after deployment.

What this script fixes:
1) Broken indentation in migrations/env.py that causes:
   NameError: name 'connectable' is not defined
2) Optional hardening for MSSQL:
   - ensure compare_type=False in online migration context to avoid DATETIME2 churn.

Usage (from project root):
  python scripts/fix_migrations_after_deploy.py
  python scripts/fix_migrations_after_deploy.py --run-upgrade
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _indent_block(lines: list[str], start: int, stop: int, spaces: int = 4) -> list[str]:
    pad = " " * spaces
    out: list[str] = []
    for i, line in enumerate(lines):
        if start <= i < stop and line.strip():
            out.append(pad + line)
        else:
            out.append(line)
    return out


def fix_env_py(env_path: Path) -> bool:
    """
    Return True if file changed.
    """
    src = _read(env_path)
    lines = src.splitlines()
    changed = False

    # Locate run_migrations_online() and trailing if context.is_offline_mode()
    run_idx = next((i for i, l in enumerate(lines) if l.strip().startswith("def run_migrations_online")), -1)
    if run_idx < 0:
        return False

    offline_idx = next((i for i, l in enumerate(lines) if l.strip().startswith("if context.is_offline_mode()")), -1)
    if offline_idx < 0:
        offline_idx = len(lines)

    # If "with connectable.connect()" exists at top-level, indent it back under function.
    top_with_idx = next(
        (
            i
            for i, l in enumerate(lines)
            if l.startswith("with connectable.connect() as connection:")
        ),
        -1,
    )
    if top_with_idx >= 0:
        # Indent from this line until before offline-mode if.
        lines = _indent_block(lines, top_with_idx, offline_idx, spaces=4)
        changed = True

    # Ensure SQL Server compare_type=False guard exists in online flow.
    text = "\n".join(lines) + "\n"
    must_have = 'kw.setdefault("compare_type", False)'
    if must_have not in text:
        needle = "with connectable.connect() as connection:\n"
        if needle in text:
            inject = (
                "with connectable.connect() as connection:\n"
                "        kw = dict(conf_args)\n"
                '        if getattr(connection.dialect, "name", None) == "mssql":\n'
                '            kw.setdefault("compare_type", False)\n\n'
                "        context.configure(\n"
                "            connection=connection,\n"
                "            target_metadata=get_metadata(),\n"
                "            **kw\n"
                "        )\n\n"
                "        with context.begin_transaction():\n"
                "            context.run_migrations()\n"
            )
            # Replace full legacy block if present
            legacy = (
                "with connectable.connect() as connection:\n"
                "        context.configure(\n"
                "            connection=connection,\n"
                "            target_metadata=get_metadata(),\n"
                "            **conf_args\n"
                "        )\n\n"
                "        with context.begin_transaction():\n"
                "            context.run_migrations()\n"
            )
            if legacy in text:
                text = text.replace(legacy, inject)
                changed = True

    if changed:
        _write(env_path, text)
    return changed


def run_upgrade(project_root: Path) -> int:
    cmd = ["flask", "db", "upgrade"]
    print(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(project_root))
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix migration files after deployment.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root (default: current directory).",
    )
    parser.add_argument(
        "--run-upgrade",
        action="store_true",
        help="Run `flask db upgrade` after applying fixes.",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    env_py = root / "migrations" / "env.py"

    if not env_py.exists():
        print(f"ERROR: {env_py} not found.", file=sys.stderr)
        return 2

    changed = fix_env_py(env_py)
    if changed:
        print(f"Fixed: {env_py}")
    else:
        print(f"No change needed: {env_py}")

    if args.run_upgrade:
        return run_upgrade(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

