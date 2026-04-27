"""Optional Fernet at-rest protection for PII (national ID) — key from environment."""

from __future__ import annotations

import hashlib
import os


def is_pii_encryption_enabled() -> bool:
    k = (os.environ.get("ESTITHMAR_ENCRYPTION_KEY") or "").strip()
    return bool(k) and k != "change-me"


def _fernet():
    if not is_pii_encryption_enabled():
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    k = (os.environ.get("ESTITHMAR_ENCRYPTION_KEY") or "").strip().encode()
    return Fernet(k)


def hash_national_id_for_search(plain: str | None) -> str | None:
    """SHA-256 hex of normalized ID for exact-match search when column is encrypted."""
    if not plain or not str(plain).strip():
        return None
    n = str(plain).strip().upper()
    return hashlib.sha256(n.encode("utf-8")).hexdigest()


def seal_national_id(plain: str | None) -> str | None:
    if plain is None or plain == "":
        return None
    f = _fernet()
    if f is None:
        return (plain or "")[:500]
    b = f.encrypt(str(plain).encode("utf-8"))
    return "e1:" + b.decode("ascii")


def open_national_id(stored: str | None) -> str | None:
    if stored is None or stored == "":
        return None
    if not (stored or "").startswith("e1:"):
        return str(stored) if stored else None
    f = _fernet()
    if f is None:
        return stored[3:500] if len(stored) > 3 else None
    try:
        return f.decrypt(stored[3:].encode("ascii")).decode("utf-8")
    except Exception:
        return str(stored)
