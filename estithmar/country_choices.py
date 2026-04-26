"""ISO 3166 country names for agent country dropdown (bundled CSV)."""

from __future__ import annotations

import csv
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _load_country_names() -> tuple[str, ...]:
    path = os.path.join(os.path.dirname(__file__), "data", "iso3166_countries.csv")
    names: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n = (row.get("name") or "").strip()
            if n:
                names.append(n)
    return tuple(sorted(set(names)))


def get_country_names() -> tuple[str, ...]:
    return _load_country_names()


def get_agent_country_choices() -> tuple[tuple[str, str], ...]:
    """(value, label) pairs for HTML selects; value is the official English short name."""
    return tuple((c, c) for c in get_country_names())


@lru_cache(maxsize=1)
def get_agent_country_value_set() -> frozenset[str]:
    return frozenset(get_country_names())


@lru_cache(maxsize=1)
def _load_country_un_region_map() -> dict[str, tuple[str, ...]]:
    """ISO country name -> UN M49-style labels from bundled CSV (region, sub-region, intermediate)."""
    path = os.path.join(os.path.dirname(__file__), "data", "iso3166_countries.csv")
    out: dict[str, tuple[str, ...]] = {}
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            vals: list[str] = []
            for key in ("region", "sub-region", "intermediate-region"):
                v = (row.get(key) or "").strip().strip('"')
                if v and v not in vals:
                    vals.append(v)
            out[name] = tuple(vals)
    return out


def get_region_choices_for_country(country: str | None) -> tuple[str, ...]:
    """Allowed region values for a standard ISO country name (empty if unknown or no country)."""
    if not country:
        return ()
    return _load_country_un_region_map().get(country, ())


def get_agent_regions_by_country_json() -> dict[str, list[str]]:
    """For embedding in agent form (country -> list of valid regions)."""
    return {k: list(v) for k, v in _load_country_un_region_map().items()}
