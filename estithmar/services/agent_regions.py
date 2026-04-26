"""Load and cache per-country region lists for agent registration (API once, then database)."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from estithmar import db
from estithmar.models import AgentCountryRegion

# Merged with API state names: common spellings and UK city-style options.
# Keys must match the official ISO 3166 English names from ``iso3166_countries.csv`` (the agent country dropdown value).
REGION_SEEDS: dict[str, list[str]] = {
    "Somalia": [
        "Banaadir",
        "Benadir",
        "Hargeisa",
        "Beledweyne",
        "Bosaso",
        "Kismayo",
        "Baidoa",
    ],
    "United Kingdom of Great Britain and Northern Ireland": [
        "London",
        "Birmingham",
        "Manchester",
        "Glasgow",
        "Liverpool",
        "Leeds",
        "Edinburgh",
        "Bristol",
        "Cardiff",
        "Belfast",
        "Newcastle upon Tyne",
        "Sheffield",
        "Nottingham",
        "Leicester",
    ],
    # US states come from the API; optional extras if the API is unavailable
    "United States of America": [
        "District of Columbia",
    ],
}

# The bundled ISO names often differ from what ``countriesnow.space`` accepts; the API can 404 on full official names.
# We still persist rows under the ISO dropdown value in ``agent_country_regions.country_name``.
COUNTRIESSNOW_COUNTRY_ALIASES: dict[str, str] = {
    "United States of America": "United States",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    # Common alternative if ever stored; API accepts these short names
    "USA": "United States",
    "U.S.A.": "United States",
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "Great Britain": "United Kingdom",
}

_STATES_API = "https://countriesnow.space/api/v0.1/countries/states"


def _api_country_name_for_request(iso_dropdown_name: str) -> str:
    """Name to send in the request body: alias or the same string."""
    c = (iso_dropdown_name or "").strip()
    return COUNTRIESSNOW_COUNTRY_ALIASES.get(c, c)


def _normalize_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def _dedupe_names(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        t = (n or "").strip()
        if not t:
            continue
        k = _normalize_key(t)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def _states_from_api(iso_country_name: str) -> list[str]:
    if not (iso_country_name or "").strip():
        return []
    request_name = _api_country_name_for_request(iso_country_name)
    body = json.dumps({"country": request_name}).encode("utf-8")
    req = urllib.request.Request(
        _STATES_API,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "EstithmarAgentRegions/1.0"},
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:  # noqa: S310 — fixed HTTPS API
            raw = resp.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not data or not data.get("data"):
        return []
    states = (data.get("data") or {}).get("states") or []
    out: list[str] = []
    for s in states:
        if not isinstance(s, dict):
            continue
        n = (s.get("name") or "").strip()
        if n:
            out.append(n)
    return out


def _row_source(name: str, from_api: list[str], seed_list: list[str]) -> str:
    if any(_normalize_key(name) == _normalize_key(a) for a in from_api):
        return "api"
    if any(_normalize_key(name) == _normalize_key(s) for s in seed_list):
        return "seed"
    return "api"


def get_region_choices_for_agent_country(country: str | None) -> tuple[str, ...]:
    """All allowed region options for a standard agent country."""
    return tuple(ensure_region_options_for_country(country))


def ensure_region_options_for_country(country: str | None) -> list[str]:
    """
    Region/city names for a country. Reads from ``agent_country_regions`` when present; otherwise
    fetches from the public API, merges with ``REGION_SEEDS``, persists, then returns.
    """
    c = (country or "").strip()[:120]
    if not c:
        return []

    q = (
        db.session.query(AgentCountryRegion.region_name)
        .filter(AgentCountryRegion.country_name == c)
        .order_by(func.lower(AgentCountryRegion.region_name))
    )
    existing = [r[0] for r in q.all()]
    if existing:
        return list(existing)

    from_api = _states_from_api(c)
    seeds = REGION_SEEDS.get(c, [])
    merged = _dedupe_names(from_api + seeds)
    if not merged:
        return []

    for name in merged:
        src = _row_source(name, from_api, seeds)
        db.session.add(AgentCountryRegion(country_name=c, region_name=name, source=src, created_at=datetime.utcnow()))

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return [
        r[0]
        for r in (
            db.session.query(AgentCountryRegion.region_name)
            .filter(AgentCountryRegion.country_name == c)
            .order_by(func.lower(AgentCountryRegion.region_name))
            .all()
        )
    ]
