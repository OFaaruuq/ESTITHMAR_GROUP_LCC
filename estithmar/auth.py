from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import LoginManager, current_user

from estithmar import db
from estithmar.models import AppUser
from estithmar.permissions import user_has_permission

login_manager = LoginManager()
login_manager.login_view = "login"


def init_auth(app):
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        u = db.session.get(AppUser, int(user_id))
        if not u or not u.is_active:
            return None
        return u


def role_required(*roles: str):
    def deco(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login", next=request.path))
            if current_user.role not in roles:
                flash("You do not have permission for this action.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return inner

    return deco


def permission_required(permission: str):
    """Require a named DB-backed permission (``Permission`` / ``permission_definitions``). Superuser passes."""

    def deco(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login", next=request.path))
            if not user_has_permission(current_user, permission):
                flash("You do not have permission for this action.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return inner

    return deco


def page_view_permission(permission: str, *, allow_member: bool = True):
    """For HTML pages: require a DB permission for staff; optionally allow ``member`` (scoped portal) without a grant.

    Use for list/detail views shared with the member portal. Post/action routes should use ``permission_required`` or other guards.
    """

    def deco(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login", next=request.path))
            if allow_member and getattr(current_user, "role", None) == "member":
                return fn(*args, **kwargs)
            if not user_has_permission(current_user, permission):
                flash("You do not have permission to view this page.", "warning")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return inner

    return deco


def any_permission_required(*keys: str):
    """User must be granted at least one of the permission keys (role defaults, grants, or superuser)."""

    def deco(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login", next=request.path))
            for k in keys:
                if k and user_has_permission(current_user, k):
                    return fn(*args, **kwargs)
            flash("You do not have permission for this action.", "danger")
            return redirect(url_for("dashboard"))

        return inner

    return deco


def admin_required(fn):
    return role_required("admin")(fn)


def ensure_default_admin():
    """Create default admin if no users exist."""
    if AppUser.query.count() > 0:
        return
    from werkzeug.security import generate_password_hash

    pwd = "admin123"
    u = AppUser(
        username="admin",
        password_hash=generate_password_hash(pwd),
        full_name="Administrator",
        role="admin",
        is_active=True,
    )
    db.session.add(u)
    db.session.commit()


def seed_if_empty():
    ensure_default_admin()
