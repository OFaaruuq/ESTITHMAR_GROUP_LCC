"""
One-time: rename public member codes from IST-* to EST-* in ``members.member_id``.

Run from project root (folder containing ``run.py`` / ``estithmar`` package), with ``.env`` configured:

    python scripts/migrate_member_ids_ist_to_est.py

Safe to run once after deploying ``MEMBER_PUBLIC_ID_PREFIX = EST``. Idempotent for rows already EST-*.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from estithmar import create_app, db
from estithmar.models import MEMBER_PUBLIC_ID_PREFIX, Member


def main() -> None:
    app = create_app()
    with app.app_context():
        legacy = "IST-"
        q = Member.query.filter(Member.member_id.like(f"{legacy}%")).order_by(Member.id.asc())
        rows = q.all()
        updated = 0
        for m in rows:
            old = m.member_id
            if not old.startswith(legacy):
                continue
            new = f"{MEMBER_PUBLIC_ID_PREFIX}-{old[len(legacy):]}"
            taken = Member.query.filter(Member.member_id == new, Member.id != m.id).first()
            if taken:
                raise RuntimeError(f"Cannot rename {old!r} to {new!r}: code already used by member id={taken.id}")
            m.member_id = new
            print(f"{old} -> {new}")
            updated += 1
        if updated:
            db.session.commit()
        print(f"Done. Updated {updated} row(s).")


if __name__ == "__main__":
    main()
