"""Database-backed permissions, role defaults, and per-user grants (least privilege)."""

from __future__ import annotations

import re
from typing import Any

from estithmar import db
from estithmar.models import (
    AppUser,
    PermissionDefinition,
    RoleDefaultPermission,
    UserGrantedPermission,
    USER_ROLES,
    get_or_create_settings,
)
from estithmar.permissions import (
    PERMISSION_CATALOG,
    default_agent_permission_keys,
    default_finance_permission_keys,
    default_operator_permission_keys,
)

KEY_RE = re.compile(r"^[a-z][a-z0-9._-]{1,80}$", re.I)


def is_valid_permission_key(key: str) -> bool:
    s = (key or "").strip()
    return bool(s and KEY_RE.match(s))


def get_assignable_role_keys_for_editor(editor: AppUser) -> list[str]:
    """Roles an admin may assign on user create/edit. Superuser may assign any known role."""
    if editor is not None and getattr(editor, "is_superuser", False):
        return [k for k, _ in USER_ROLES]
    s = get_or_create_settings()
    ex = s.get_extra() if s else {}
    raw = ex.get("assignable_user_roles")
    allowed = {k for k, _ in USER_ROLES}
    if isinstance(raw, list) and raw:
        return [r for r in raw if r in allowed]
    # Default: all except admin (use superuser to promote to admin)
    return [k for k, _ in USER_ROLES if k != "admin"]


def set_assignable_user_roles(roles: list[str]) -> None:
    s = get_or_create_settings()
    ex = s.get_extra()
    allowed = {k for k, _ in USER_ROLES}
    cleaned = [r for r in roles if r in allowed and r != "admin"]
    ex["assignable_user_roles"] = cleaned
    s.set_extra(ex)
    db.session.commit()


def effective_permission_keys_for_user(user: AppUser) -> set[str]:
    if user is None or not getattr(user, "is_active", True):
        return set()
    if getattr(user, "is_superuser", False):
        q = db.session.query(PermissionDefinition.key).filter(PermissionDefinition.is_active)
        return {r[0] for r in q.all()}
    role = (getattr(user, "role", None) or "").strip() or "member"
    pids: set[int] = set()
    pids |= {
        r[0]
        for r in (
            db.session.query(RoleDefaultPermission.permission_id)
            .filter(RoleDefaultPermission.role == role)
            .all()
        )
    }
    pids |= {
        r[0]
        for r in (
            db.session.query(UserGrantedPermission.permission_id).filter(UserGrantedPermission.user_id == user.id).all()
        )
    }
    if not pids:
        return set()
    return {
        r[0]
        for r in (
            db.session.query(PermissionDefinition.key)
            .filter(
                PermissionDefinition.id.in_(pids),
                PermissionDefinition.is_active,
            )
            .all()
        )
    }


def user_has_permission_dbc(user: Any, permission_key: str) -> bool:
    if user is None or not getattr(user, "is_active", True):
        return False
    key = (permission_key or "").strip()
    if not key:
        return False
    u = user if isinstance(user, AppUser) else AppUser.query.get(getattr(user, "id", None))
    if u is None:
        return False
    if getattr(u, "is_superuser", False):
        return True
    eff = effective_permission_keys_for_user(u)
    return key in eff


def _ensure_permission_row(key: str, label: str, description: str, sort_order: int) -> PermissionDefinition:
    p = db.session.query(PermissionDefinition).filter_by(key=key).first()
    if p:
        return p
    p = PermissionDefinition(
        key=key, label=label, description=description, sort_order=sort_order, is_active=True
    )
    db.session.add(p)
    db.session.flush()
    return p


def ensure_rbac_seed() -> None:
    """Idempotent: default permission catalog + role defaults. Called after schema exists."""
    from sqlalchemy import inspect

    insp = inspect(db.engine) if db.engine else None
    if insp is None or not insp.has_table("permission_definitions"):
        return

    perm_by_key: dict[str, PermissionDefinition] = {}
    for key, label, desc, so in PERMISSION_CATALOG:
        perm_by_key[key] = _ensure_permission_row(key, label, desc, so)

    def link(role: str, key: str) -> None:
        p = perm_by_key.get(key)
        if not p:
            return
        ex = (
            db.session.query(RoleDefaultPermission.id)
            .filter(
                RoleDefaultPermission.role == role,
                RoleDefaultPermission.permission_id == p.id,
            )
            .first()
        )
        if ex:
            return
        db.session.add(RoleDefaultPermission(role=role, permission_id=p.id))

    for key in perm_by_key:
        link("admin", key)
    for key in default_operator_permission_keys():
        link("operator", key)
    for key in default_finance_permission_keys():
        link("finance", key)
    for key in default_agent_permission_keys():
        link("agent", key)

    db.session.commit()
    s = get_or_create_settings()
    d = s.get_extra()
    if d.get("assignable_user_roles") is None:
        d["assignable_user_roles"] = ["operator", "finance", "agent", "member"]
        s.set_extra(d)
        db.session.commit()


def sync_user_grants(user: AppUser, permission_ids: list[int]) -> None:
    want = {i for i in permission_ids if i and i > 0}
    existing = {r.permission_id for r in user.extra_permissions.all()}
    for pid in existing - want:
        UserGrantedPermission.query.filter_by(user_id=user.id, permission_id=pid).delete()
    for pid in want - existing:
        db.session.add(UserGrantedPermission(user_id=user.id, permission_id=pid))
    db.session.flush()


def permission_in_use(permission_id: int) -> bool:
    a = (
        db.session.query(RoleDefaultPermission.id)
        .filter(RoleDefaultPermission.permission_id == permission_id)
        .first()
    )
    b = (
        db.session.query(UserGrantedPermission.id)
        .filter(UserGrantedPermission.permission_id == permission_id)
        .first()
    )
    return bool(a or b)
