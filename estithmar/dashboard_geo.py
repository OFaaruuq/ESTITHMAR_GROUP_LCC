"""Dashboard: one map marker per agent (country-based), with jitter when agents share a country."""

from __future__ import annotations

import math
from typing import Any

from estithmar import db
from estithmar.models import Agent, Member

# Approximate country centers (lat, lng) — ISO 3166-1 alpha-2
ISO2_CENTER: dict[str, tuple[float, float]] = {
    "AE": (23.4241, 53.8478),
    "AR": (-38.4161, -63.6167),
    "AU": (-25.2744, 133.7751),
    "BH": (26.0667, 50.5577),
    "BD": (23.6850, 90.3563),
    "BR": (-14.2350, -51.9253),
    "CA": (56.1304, -106.3468),
    "CN": (35.8617, 104.1954),
    "DJ": (11.8251, 42.5903),
    "EG": (26.8206, 30.8025),
    "ET": (9.1450, 40.4897),
    "DE": (51.1657, 10.4515),
    "ES": (40.4637, -3.7492),
    "FR": (46.2276, 2.2137),
    "GB": (55.3781, -3.4360),
    "IN": (20.5937, 78.9629),
    "ID": (-0.7893, 113.9213),
    "IQ": (33.2232, 43.6793),
    "IR": (32.4279, 53.6880),
    "IT": (41.8719, 12.5674),
    "JO": (30.5852, 36.2384),
    "JP": (36.2048, 138.2529),
    "KE": (-0.0236, 37.9062),
    "KW": (29.3117, 47.4818),
    "LB": (33.8547, 35.8623),
    "LY": (26.3351, 17.228331),
    "MY": (4.2105, 101.9758),
    "MA": (31.7917, -7.0926),
    "NL": (52.1326, 5.2913),
    "NG": (9.0820, 8.6753),
    "NO": (60.4720, 8.4689),
    "OM": (21.4735, 55.9754),
    "PK": (30.3753, 69.3451),
    "PH": (12.8797, 121.7740),
    "PL": (51.9194, 19.1451),
    "QA": (25.3548, 51.1839),
    "RU": (61.5240, 105.3188),
    "SA": (23.8859, 45.0792),
    "SO": (5.1521, 46.1996),
    "ZA": (-30.5595, 22.9375),
    "KR": (35.9078, 127.7669),
    "SD": (12.8628, 30.2176),
    "SE": (60.1282, 18.6435),
    "CH": (46.8182, 8.2275),
    "SY": (34.8021, 38.9968),
    "TZ": (-6.3690, 34.8888),
    "TH": (15.8700, 100.9925),
    "TR": (38.9637, 35.2433),
    "UA": (48.3794, 31.1656),
    "US": (37.0902, -95.7129),
    "YE": (15.5527, 48.5164),
    "MX": (23.6345, -102.5528),
    "FI": (61.9241, 25.7482),
}

COUNTRY_ALIASES: dict[str, str] = {
    "united states": "US",
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "england": "GB",
    "somalia": "SO",
    "kenya": "KE",
    "ethiopia": "ET",
    "djibouti": "DJ",
    "uae": "AE",
    "united arab emirates": "AE",
    "saudi arabia": "SA",
    "saudi": "SA",
    "egypt": "EG",
    "sudan": "SD",
    "germany": "DE",
    "france": "FR",
    "india": "IN",
    "china": "CN",
    "canada": "CA",
    "australia": "AU",
    "netherlands": "NL",
    "holland": "NL",
    "italy": "IT",
    "spain": "ES",
    "turkey": "TR",
    "türkiye": "TR",
    "south africa": "ZA",
    "nigeria": "NG",
    "morocco": "MA",
    "yemen": "YE",
    "oman": "OM",
    "qatar": "QA",
    "kuwait": "KW",
    "bahrain": "BH",
    "jordan": "JO",
    "lebanon": "LB",
    "syria": "SY",
    "iraq": "IQ",
    "iran": "IR",
    "pakistan": "PK",
    "bangladesh": "BD",
    "indonesia": "ID",
    "malaysia": "MY",
    "philippines": "PH",
    "japan": "JP",
    "south korea": "KR",
    "korea": "KR",
    "russia": "RU",
    "brazil": "BR",
    "mexico": "MX",
    "argentina": "AR",
    "sweden": "SE",
    "norway": "NO",
    "finland": "FI",
    "poland": "PL",
    "ukraine": "UA",
    "switzerland": "CH",
    "tanzania": "TZ",
    "thailand": "TH",
    "libya": "LY",
}


def _normalize_country_to_iso2(country: str | None) -> str | None:
    if not country or not str(country).strip():
        return None
    k = str(country).strip().lower()
    if len(k) == 2 and k.isalpha():
        up = k.upper()
        return up if up in ISO2_CENTER else None
    return COUNTRY_ALIASES.get(k)


def _jitter(lat: float, lng: float, index: int) -> tuple[float, float]:
    """Spread overlapping agents in the same country (small offset in degrees)."""
    if index == 0:
        return lat, lng
    angle = (index * 137.508) * (math.pi / 180.0)
    r = 0.22 + index * 0.18
    return lat + r * math.cos(angle) * 0.55, lng + r * math.sin(angle) * 0.55


def _member_count_for_agent(agent_id: int, mids: list[int] | None) -> int:
    q = Member.query.filter(Member.agent_id == agent_id)
    if mids is not None:
        if not mids:
            return 0
        q = q.filter(Member.id.in_(mids))
    return q.count()


def _agents_query_for_user(user_role: str | None, user_agent_id: int | None):
    """Agents visible on the dashboard map (every agent for admins; own record for field agents)."""
    if user_role == "agent" and user_agent_id:
        return Agent.query.filter(Agent.id == user_agent_id)
    return Agent.query.order_by(Agent.status.desc(), Agent.full_name, Agent.agent_id)


def build_members_region_map_data(
    mids: list[int] | None,
    *,
    user_role: str | None = None,
    user_agent_id: int | None = None,
) -> dict[str, Any]:
    """
    One marker per agent (when country resolves to a known center).
    Admins see all active agents; agents see only their own agent row.

    mids: member-id scope for counts (None = all members).
    """
    agents: list[Agent] = list(_agents_query_for_user(user_role, user_agent_id).all())

    rows: list[dict[str, Any]] = []
    by_iso: dict[str, list[Agent]] = {}
    for ag in agents:
        c = (ag.country or "").strip()
        r = (ag.region or "").strip() or "—"
        iso = _normalize_country_to_iso2(c) if c else None
        cnt = _member_count_for_agent(ag.id, mids)
        on_map = bool(iso and iso in ISO2_CENTER)
        rows.append(
            {
                "label": ag.full_name or "—",
                "agent_id": ag.agent_id,
                "region": r,
                "country": c or "—",
                "count": int(cnt),
                "on_map": on_map,
                "iso2": iso,
            }
        )
        if on_map and iso:
            by_iso.setdefault(iso, []).append(ag)

    rows.sort(key=lambda x: (-x["count"], x["label"]))

    # Orphan members (no agent) — only relevant for admin/global view
    orphan_count = 0
    if user_role != "agent":
        oq = Member.query.filter(Member.agent_id.is_(None))
        if mids is not None:
            if mids:
                oq = oq.filter(Member.id.in_(mids))
            else:
                oq = oq.filter(Member.id == -1)
        orphan_count = oq.count()
    if orphan_count and user_role != "agent":
        rows.append(
            {
                "label": "Members without agent",
                "agent_id": "",
                "region": "",
                "country": "",
                "count": int(orphan_count),
                "on_map": False,
                "iso2": None,
                "is_orphan": True,
            }
        )

    markers: list[dict[str, Any]] = []
    for iso, group in sorted(by_iso.items()):
        group_sorted = sorted(group, key=lambda a: (a.full_name or "", a.id))
        for i, ag in enumerate(group_sorted):
            lat0, lng0 = ISO2_CENTER[iso]
            lat, lng = _jitter(lat0, lng0, i)
            cnt = _member_count_for_agent(ag.id, mids)
            r = (ag.region or "").strip() or "—"
            c = (ag.country or "").strip()
            name = f"{ag.full_name} ({ag.agent_id}) · {cnt} member{'s' if cnt != 1 else ''}"
            if r and r != "—":
                name += f" · {r}"
            if c:
                name += f", {c}"
            markers.append({"name": name[:200], "coords": [lat, lng]})

    total_members = sum(int(r["count"]) for r in rows)
    mapped_member_count = sum(int(r["count"]) for r in rows if r.get("on_map"))
    unmapped_member_count = total_members - mapped_member_count

    agent_rows = [r for r in rows if not r.get("is_orphan")]
    agents_on_map = sum(1 for r in agent_rows if r.get("on_map"))
    total_agents = len(agent_rows)

    return {
        "markers": markers,
        "rows": rows,
        "has_markers": len(markers) > 0,
        "total_members": int(total_members),
        "mapped_member_count": int(mapped_member_count),
        "unmapped_member_count": int(unmapped_member_count),
        "agents_on_map": int(agents_on_map),
        "total_agents": int(total_agents),
        "agents_off_map": int(total_agents - agents_on_map),
    }
