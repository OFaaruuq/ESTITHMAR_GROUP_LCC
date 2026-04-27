"""Server-side device signal (HTTP headers) — stable per-browser fingerprint hash."""

from __future__ import annotations

import hashlib
from typing import Any


def request_device_fingerprint(request: Any) -> str:
    if request is None:
        return ""
    h = request.headers
    parts = [
        (h.get("User-Agent") or h.get("user-agent") or "")[:800],
        (h.get("Accept-Language") or "")[:200],
        (h.get("Accept-Encoding") or "")[:120],
        (h.get("Sec-CH-UA") or h.get("Sec-CH-UA-Platform") or h.get("Sec-CH-UA-Mobile") or "")
        or (h.get("X-Client-Data") or ""),
    ]
    raw = "|".join(p if isinstance(p, str) else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
