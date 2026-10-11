"""Thin client for ESPN's public football (soccer) endpoints.

The core API lists every event of a club across all competitions, which is what
lets this integration follow one team without configuring each competition.
The site "summary" endpoint then gives score, status, goals, cards and lineups,
and the standings endpoint the league table with qualification zones.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp

from .const import LEAGUE_NAMES

CORE = "https://sports.core.api.espn.com/v2/sports/soccer"
SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer"
SEARCH = "https://site.web.api.espn.com/apis/common/v3/search"

_REF_RE = re.compile(r"leagues/([^/?]+)/events/(\d+)")
_TIMEOUT = aiohttp.ClientTimeout(total=20)


class EspnError(Exception):
    """Raised when ESPN cannot be reached or returns garbage."""


class EspnClient:
    """Fetch and normalise ESPN football data."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict:
        try:
            async with self._session.get(url, params=params, timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise EspnError(f"{url}: {err}") from err

    async def search_teams(self, query: str) -> list[dict[str, str]]:
        data = await self._get(
            SEARCH, {"query": query, "type": "team", "sport": "soccer", "limit": 20}
        )
        teams = []
        for item in data.get("items", []):
            if item.get("sport") != "soccer" or not item.get("id"):
                continue
            name = item.get("displayName") or item["id"]
            # Men's and women's sides share a name; their home competition tells them apart.
            league = item.get("defaultLeagueSlug") or item.get("league")
            label = f"{name} · {league}" if league else name
            teams.append({"id": str(item["id"]), "name": name, "label": label})
        return teams

    async def team_events(self, team_id: str, year: int) -> dict[str, str]:
        """Return {event_id: league_slug} for one team and calendar year."""
        data = await self._get(
            f"{CORE}/teams/{team_id}/events", {"dates": year, "limit": 500}
        )
        result: dict[str, str] = {}
        for item in data.get("items", []):
            if match := _REF_RE.search(item.get("$ref", "")):
                result[match.group(2)] = match.group(1)
        return result

    async def summary(self, league: str, event_id: str) -> dict:
        return await self._get(f"{SITE}/{league}/summary", {"event": event_id})

    async def standings(self, league: str) -> dict:
        return await self._get(f"{STANDINGS}/{league}/standings")

    async def league_logos(self, league: str) -> dict[str, str]:
        """Return {"light": url, "dark": url} for a competition (may be empty)."""
        data = await self._get(f"{SITE}/{league}/scoreboard")
        logos: dict[str, str] = {}
        for league_info in data.get("leagues") or []:
            for logo in league_info.get("logos") or []:
                href = logo.get("href") or ""
                if not href or "default-team-logo" in href:
                    continue  # ESPN's placeholder, e.g. for the Supercup
                logos["dark" if "dark" in (logo.get("rel") or []) else "light"] = href
        return logos


def short_league(name: str) -> str:
    return LEAGUE_NAMES.get(name, name)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _logo(team: dict) -> str | None:
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href")
    if team.get("logo"):
        return team["logo"]
    return f"https://a.espncdn.com/i/teamlogos/soccer/500/{team['id']}.png" if team.get("id") else None


def _team(competitor: dict) -> dict[str, Any]:
    team = competitor.get("team", {})
    name = team.get("displayName") or team.get("name") or "?"
    return {
        "id": str(team.get("id", "")),
        "name": name,
        "short": team.get("shortDisplayName") or name,
        "abbr": team.get("abbreviation") or name[:3].upper(),
        "color": team.get("color"),
        "logo": _logo(team),
        "score": _int(competitor.get("score")),
        "shootout": _int(competitor.get("shootoutScore")),
        "winner": competitor.get("winner"),
        "form": competitor.get("form"),
    }


def _event_kind(text: str, scoring: bool) -> str | None:
    t = text.lower()
    if "own goal" in t:
        return "own_goal"
    if "penalty" in t and scoring:
        return "penalty"
    if scoring:
        return "goal"
    if "red card" in t or "second yellow" in t:
        return "red"
    if "yellow card" in t:
        return "yellow"
    return None


def parse_summary(league: str, event_id: str, data: dict) -> dict[str, Any]:
    """Normalise a summary payload into match, timeline and lineups."""
    header = data.get("header", {})
    comp = (header.get("competitions") or [{}])[0]
    league_info = header.get("league", {})
    season = header.get("season", {})
    status = comp.get("status", {})
    stype = status.get("type", {})

    home = away = None
    for competitor in comp.get("competitors", []):
        if competitor.get("homeAway") == "home":
            home = _team(competitor)
        else:
            away = _team(competitor)
    if home is None or away is None:
        raise EspnError(f"event {event_id} has no competitors")

    # "2025-26 UEFA Champions League, League Phase" -> season 2025/26, round "League Phase"
    season_name = season.get("name") or ""
    round_name = season_name.split(", ", 1)[1] if ", " in season_name else None
    years = re.match(r"(\d{4})-(\d{2})", season_name)
    season_label = f"{years.group(1)}/{years.group(2)}" if years else str(season.get("year", ""))

    timeline = []
    for k in data.get("keyEvents") or []:
        if k.get("shootout"):
            continue
        kind = _event_kind((k.get("type") or {}).get("text", ""), bool(k.get("scoringPlay")))
        if not kind:
            continue
        people = [
            (p.get("athlete") or {}).get("displayName")
            for p in k.get("participants") or []
        ]
        timeline.append(
            {
                "kind": kind,
                "team_id": str((k.get("team") or {}).get("id", "")),
                "player": people[0] if people else None,
                "assist": people[1] if kind == "goal" and len(people) > 1 else None,
                "minute": (k.get("clock") or {}).get("displayValue"),
            }
        )

    venue = (data.get("gameInfo") or {}).get("venue") or {}
    clock = status.get("displayClock")
    if stype.get("state") != "in":
        clock = None

    match = {
        "id": event_id,
        "league_id": league,
        "league": short_league(league_info.get("name") or ""),
        "season": season.get("year"),
        "season_label": season_label,
        "round": round_name,
        "date": comp.get("date") or header.get("date"),
        "state": stype.get("state", "pre"),
        "status": stype.get("name", ""),
        "status_detail": stype.get("shortDetail") or stype.get("detail") or "",
        "clock": clock,
        "period": status.get("period"),
        "venue": venue.get("fullName"),
        "city": (venue.get("address") or {}).get("city"),
        "home": home,
        "away": away,
    }
    return {
        "match": match,
        "timeline": timeline,
        "lineups": _lineups(data.get("rosters") or []),
    }


def _lineups(rosters: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for roster in rosters:
        team_id = str((roster.get("team") or {}).get("id", ""))
        players = []
        for p in roster.get("roster") or []:
            athlete = p.get("athlete") or {}
            players.append(
                {
                    "no": _int(p.get("jersey")),
                    "name": athlete.get("displayName") or athlete.get("fullName"),
                    "pos": (p.get("position") or {}).get("abbreviation"),
                    "starter": bool(p.get("starter")),
                    "place": _int(p.get("formationPlace")),
                    "in": bool(p.get("subbedIn")),
                    "out": bool(p.get("subbedOut")),
                }
            )
        players.sort(
            key=lambda x: (
                not x["starter"],
                x["place"] if x["place"] else 99,
                x["no"] if x["no"] is not None else 99,
            )
        )
        if team_id and players:
            result[team_id] = {"formation": roster.get("formation"), "players": players}
    return result


def parse_standings(data: dict) -> list[dict]:
    """League table(s) with qualification-zone colours."""
    groups = []
    for child in data.get("children") or []:
        entries = (child.get("standings") or {}).get("entries") or []
        rows = []
        for entry in entries:
            team = entry.get("team") or {}
            stats = {
                (s.get("abbreviation") or s.get("name")): s.get("displayValue")
                for s in entry.get("stats", [])
            }
            note = entry.get("note") or {}
            rows.append(
                {
                    "rank": _int(stats.get("R")),
                    "id": str(team.get("id", "")),
                    "name": team.get("displayName", "?"),
                    "short": team.get("shortDisplayName") or team.get("displayName", "?"),
                    "abbr": team.get("abbreviation"),
                    "logo": _logo(team),
                    "gp": stats.get("GP"),
                    "w": stats.get("W"),
                    "d": stats.get("D"),
                    "l": stats.get("L"),
                    "gf": stats.get("F"),
                    "ga": stats.get("A"),
                    "gd": stats.get("GD"),
                    "pts": stats.get("P"),
                    "zone": note.get("color"),
                    "zone_name": note.get("description"),
                }
            )
        rows.sort(key=lambda r: r["rank"] if r["rank"] is not None else 999)
        if rows:
            groups.append({"name": child.get("name") or "", "rows": rows})
    if len(groups) == 1:
        groups[0]["name"] = ""
    return groups
