"""
Change/reset an admin user password from CLI.

Usage examples:
  python scripts/change_admin_password.py --username admin --password "NewStrongPass123!"
  python scripts/change_admin_password.py --email admin@example.com --prompt
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

# Ensure project root is importable even when running from ./scripts
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from estithmar import create_app, db
from estithmar.models import AppUser


def _read_password_interactive() -> str:
    p1 = getpass.getpass("New password: ")
    p2 = getpass.getpass("Confirm password: ")
    if p1 != p2:
        raise ValueError("Passwords do not match.")
    return p1


def main() -> int:
    parser = argparse.ArgumentParser(description="Change/reset admin password.")
    parser.add_argument("--username", help="Admin username")
    parser.add_argument("--email", help="Admin email")
    parser.add_argument("--password", help="New password (avoid shell history in production)")
    parser.add_argument("--prompt", action="store_true", help="Prompt password securely")
    args = parser.parse_args()

    if not args.username and not args.email:
        print("ERROR: provide --username or --email", file=sys.stderr)
        return 2
    if not args.password and not args.prompt:
        print("ERROR: provide --password or --prompt", file=sys.stderr)
        return 2

    try:
        new_password = args.password if args.password else _read_password_interactive()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not new_password or len(new_password) < 8:
        print("ERROR: password must be at least 8 characters.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        q = AppUser.query
        if args.username:
            q = q.filter_by(username=args.username.strip())
        elif args.email:
            q = q.filter_by(email=args.email.strip().lower())
        user = q.first()
        if not user:
            print("ERROR: admin user not found.", file=sys.stderr)
            return 3
        if (user.role or "").strip().lower() != "admin":
            print(f"ERROR: user '{user.username}' is role='{user.role}', not admin.", file=sys.stderr)
            return 4

        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        print(f"Password updated for admin user: {user.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

