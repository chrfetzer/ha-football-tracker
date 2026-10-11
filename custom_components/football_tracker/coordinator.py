"""Data coordinator: follows one club across all competitions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EspnClient, EspnError, parse_standings, parse_summary
from .const import (
    CONF_BROADCASTS,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_FRIENDLIES,
    CONF_KICKOFF_NOTICE,
    CONF_TEAM_ID,
    CONF_TEAM_NAME,
    DEFAULT_BROADCASTS,
    DEFAULT_HISTORY_YEARS,
    DEFAULT_KICKOFF_NOTICE,
    DOMAIN,
    EVENT_TYPE,
    FRIENDLY_LEAGUES,
    INDEX_MAX_AGE,
    INTERVAL_IDLE,
    INTERVAL_LIVE,
    INTERVAL_SOON,
    LIVE_WINDOW_AFTER,
    LIVE_WINDOW_BEFORE,
    LOGGER,
    STANDINGS_MAX_AGE,
    UPCOMING_MAX_AGE,
    UPCOMING_NEAR_MAX_AGE,
)

STORAGE_VERSION = 1
_FETCH_LIMIT = asyncio.Semaphore(4)
# Tables are only fetched for competitions with a match in this window.
_TABLE_WINDOW = timedelta(days=120)
# Team fields the card needs; the attribute set is pushed to every dashboard on each update.
_MATCH_TEAM_KEYS = ("id", "name", "abbr", "logo", "score", "shootout")

type FootballConfigEntry = ConfigEntry[FootballCoordinator]


def parse_broadcast_rules(text: str) -> list[tuple[str, list[str]]]:
    """Parse "competition substring = channel, channel" lines."""
    rules = []
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        key, _, channels = line.partition("=")
        names = [c.strip() for c in channels.split(",") if c.strip()]
        if key.strip() and names:
            rules.append((key.strip().lower(), names))
    return rules


def channels_for(league: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    fallback: list[str] = []
    for key, names in rules:
        if key == "*":
            fallback = names
        elif key in league.lower():
            return names
    return fallback


def result_for(us: dict, them: dict) -> str | None:
    if us["score"] is None or them["score"] is None:
        return None
    if us["score"] != them["score"]:
        return "W" if us["score"] > them["score"] else "L"
    if us["shootout"] is not None and them["shootout"] is not None:
        return "W" if us["shootout"] > them["shootout"] else "L"
    return "D"


class FootballCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls ESPN; fast while a match is live, slow otherwise."""

    config_entry: FootballConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FootballConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_TEAM_NAME]}",
            update_interval=INTERVAL_IDLE,
        )
        self.api = EspnClient(async_get_clientsession(hass))
        self.team_id: str = entry.data[CONF_TEAM_ID]
        self.team_name: str = entry.data[CONF_TEAM_NAME]
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{self.team_id}")
        self._index: dict[str, str] = {}
        self._index_at: datetime | None = None
        self._matches: dict[str, dict] = {}
        self._fetched_at: dict[str, datetime] = {}
        self._timelines: dict[str, list] = {}
        self._lineups: dict[str, dict] = {}
        self._standings: dict[str, dict] = {}
        self._standings_at: dict[str, datetime] = {}
        self._league_logos: dict[str, dict[str, str]] = {}
        self._kickoff_noticed: set[str] = set()
        self._team_info: dict[str, Any] = {"id": self.team_id, "name": self.team_name}

    @property
    def _options(self) -> dict[str, Any]:
        return self.config_entry.options

    async def _async_setup(self) -> None:
        stored = await self._store.async_load() or {}
        for match in stored.get("finished", {}).values():
            self._matches[match["id"]] = match
        self._timelines.update(stored.get("timelines", {}))

    # ------------------------------------------------------------------ fetching

    async def _refresh_index(self, now: datetime) -> None:
        years_back = int(self._options.get(CONF_HISTORY_YEARS, DEFAULT_HISTORY_YEARS))
        years = range(now.year - years_back + 1, now.year + 2)
        results = await asyncio.gather(
            *(self.api.team_events(self.team_id, y) for y in years), return_exceptions=True
        )
        index: dict[str, str] = {}
        for result in results:
            if isinstance(result, Exception):
                raise result
            index.update(result)
        if not self._options.get(CONF_INCLUDE_FRIENDLIES, False):
            index = {e: lg for e, lg in index.items() if lg not in FRIENDLY_LEAGUES}
        self._index = index
        self._index_at = now
        for stale in set(self._matches) - set(index):
            self._matches.pop(stale, None)

    def _needs_fetch(self, event_id: str, now: datetime) -> bool:
        match = self._matches.get(event_id)
        if match is None:
            return True
        if match["state"] == "post":
            return False
        if match["state"] == "in":
            return True
        kickoff = _parse_dt(match["date"])
        if kickoff is None:
            return True
        if kickoff - LIVE_WINDOW_BEFORE <= now <= kickoff + LIVE_WINDOW_AFTER:
            return True
        last = self._fetched_at.get(event_id)
        if last is None:
            return True
        max_age = UPCOMING_NEAR_MAX_AGE if kickoff - now < timedelta(days=1) else UPCOMING_MAX_AGE
        return now - last > max_age

    async def _fetch(self, event_id: str) -> dict | None:
        league = self._index[event_id]
        async with _FETCH_LIMIT:
            try:
                return parse_summary(league, event_id, await self.api.summary(league, event_id))
            except EspnError as err:
                LOGGER.debug("Could not fetch event %s: %s", event_id, err)
                return None

    async def _fetch_table(self, league: str) -> tuple[str, list | None]:
        async with _FETCH_LIMIT:
            try:
                return league, parse_standings(await self.api.standings(league))
            except EspnError as err:
                LOGGER.debug("Could not fetch table %s: %s", league, err)
                return league, None

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        if self._index_at is None or now - self._index_at > INDEX_MAX_AGE:
            try:
                await self._refresh_index(now)
            except EspnError as err:
                if not self._index:
                    raise UpdateFailed(f"ESPN not reachable: {err}") from err
                LOGGER.warning("Keeping old fixture list, ESPN error: %s", err)

        due = [eid for eid in self._index if self._needs_fetch(eid, now)]
        parsed = await asyncio.gather(*(self._fetch(eid) for eid in due))
        newly_finished: set[str] = set()
        for result in parsed:
            if result is None:
                continue
            match = result["match"]
            eid = match["id"]
            previous = self._matches.get(eid)
            self._capture_team_info(match)
            self._fire_events(previous, match, self._timelines.get(eid, []), result["timeline"], now)
            if match["state"] == "post" and (previous is None or previous["state"] != "post"):
                newly_finished.add(match["league_id"])
            self._matches[eid] = match
            self._fetched_at[eid] = now
            self._timelines[eid] = result["timeline"]
            if result["lineups"]:
                self._lineups[eid] = result["lineups"]

        await self._refresh_tables(now, newly_finished)
        await self._refresh_league_logos()
        if newly_finished:
            self._save()
        self.update_interval = self._next_interval(now)
        return self._build(now)

    async def _refresh_tables(self, now: datetime, force: set[str]) -> None:
        recent = {
            m["league_id"]
            for m in self._matches.values()
            if (kickoff := _parse_dt(m["date"])) and abs(kickoff - now) < _TABLE_WINDOW
        }
        due = [
            lg
            for lg in recent
            if lg in force
            or lg not in self._standings_at
            or now - self._standings_at[lg] > STANDINGS_MAX_AGE
        ]
        for league, groups in await asyncio.gather(*(self._fetch_table(lg) for lg in due)):
            if groups is None:
                continue
            self._standings_at[league] = now
            if groups:
                self._standings[league] = {"groups": groups}
            else:
                self._standings.pop(league, None)

    async def _refresh_league_logos(self) -> None:
        """Competition logos rarely change: fetch each once per Home Assistant run."""
        missing = sorted(set(self._index.values()) - set(self._league_logos))

        async def fetch(league: str) -> None:
            async with _FETCH_LIMIT:
                try:
                    self._league_logos[league] = await self.api.league_logos(league)
                except EspnError as err:
                    LOGGER.debug("Could not fetch logo for %s: %s", league, err)

        await asyncio.gather(*(fetch(lg) for lg in missing))

    def _capture_team_info(self, match: dict) -> None:
        for side in ("home", "away"):
            team = match[side]
            if team["id"] == self.team_id:
                self._team_info = {
                    "id": self.team_id,
                    "name": team["name"],
                    "short": team["short"],
                    "abbr": team["abbr"],
                    "color": team["color"],
                    "logo": team["logo"],
                }

    def _save(self) -> None:
        finished = {k: m for k, m in self._matches.items() if m["state"] == "post"}
        timelines = {k: t for k, t in self._timelines.items() if k in finished}
        self._store.async_delay_save(
            lambda: {"finished": finished, "timelines": timelines}, 5
        )

    def _next_interval(self, now: datetime) -> timedelta:
        soonest = None
        for match in self._matches.values():
            if match["state"] == "in":
                return INTERVAL_LIVE
            if match["state"] != "pre":
                continue
            kickoff = _parse_dt(match["date"])
            if kickoff is None:
                continue
            if kickoff - LIVE_WINDOW_BEFORE <= now <= kickoff + LIVE_WINDOW_AFTER:
                return INTERVAL_LIVE
            if kickoff > now and (soonest is None or kickoff < soonest):
                soonest = kickoff
        if soonest is not None:
            until = soonest - now
            if until < timedelta(hours=3):
                # Wake up right when the live window opens.
                return max(min(INTERVAL_SOON, until - LIVE_WINDOW_BEFORE), INTERVAL_LIVE)
        return INTERVAL_IDLE

    # ------------------------------------------------------------------ events

    def _fire_events(
        self, prev: dict | None, match: dict, old_tl: list, new_tl: list, now: datetime
    ) -> None:
        eid = match["id"]
        notice = timedelta(
            minutes=int(self._options.get(CONF_KICKOFF_NOTICE, DEFAULT_KICKOFF_NOTICE))
        )
        kickoff = _parse_dt(match["date"])
        if (
            match["state"] == "pre"
            and kickoff
            and now < kickoff <= now + notice
            and eid not in self._kickoff_noticed
        ):
            self._kickoff_noticed.add(eid)
            self._fire("kickoff_soon", match, minutes=round((kickoff - now).seconds / 60))

        if prev is None:
            return
        if prev["state"] == "pre" and match["state"] == "in":
            self._fire("kickoff", match)

        seen = {_key(e) for e in old_tl}
        fresh = [e for e in new_tl if _key(e) not in seen]

        for side in ("home", "away"):
            old, new = prev[side]["score"] or 0, match[side]["score"] or 0
            team = match[side]
            if new > old:
                goals = [e for e in fresh if e["team_id"] == team["id"] and e["kind"] in ("goal", "penalty", "own_goal")]
                for i in range(new - old):
                    goal = goals[i] if i < len(goals) else {}
                    self._fire(
                        "goal",
                        match,
                        scoring_team=team["name"],
                        scoring_team_id=team["id"],
                        for_us=team["id"] == self.team_id,
                        goal_type=goal.get("kind", "goal"),
                        player=goal.get("player"),
                        assist=goal.get("assist"),
                        minute=goal.get("minute") or match["clock"],
                    )
            elif new < old:
                # VAR or a data correction took a goal back.
                self._fire(
                    "goal_cancelled",
                    match,
                    scoring_team=team["name"],
                    scoring_team_id=team["id"],
                    for_us=team["id"] == self.team_id,
                )

        for card in (e for e in fresh if e["kind"] == "red"):
            self._fire(
                "red_card",
                match,
                card_team_id=card["team_id"],
                for_us=card["team_id"] == self.team_id,
                player=card["player"],
                minute=card["minute"],
            )
        if prev["status"] != match["status"] and match["status"] == "STATUS_HALFTIME":
            self._fire("halftime", match)
        if prev["state"] != "post" and match["state"] == "post":
            self._fire("full_time", match)

    def _sides(self, match: dict) -> tuple[dict, dict]:
        home, away = match["home"], match["away"]
        return (home, away) if home["id"] == self.team_id else (away, home)

    def _fire(self, kind: str, match: dict, **extra: Any) -> None:
        us, them = self._sides(match)
        data = {
            "type": kind,
            "team_id": self.team_id,
            "team": self.team_name,
            "match_id": match["id"],
            "competition": match["league"],
            "round": match["round"],
            "home": match["home"]["name"],
            "away": match["away"]["name"],
            "home_score": match["home"]["score"],
            "away_score": match["away"]["score"],
            "opponent": them["name"],
            "team_score": us["score"],
            "opponent_score": them["score"],
            "clock": match["clock"],
            "tv": self._channels(match),
            **extra,
        }
        if kind == "full_time":
            data["result"] = result_for(us, them)
            data["team_shootout"] = us["shootout"]
            data["opponent_shootout"] = them["shootout"]
        LOGGER.debug("Firing %s: %s", EVENT_TYPE, data)
        self.hass.bus.async_fire(EVENT_TYPE, data)

    # ------------------------------------------------------------------ output

    def _channels(self, match: dict) -> list[str]:
        rules = parse_broadcast_rules(self._options.get(CONF_BROADCASTS, DEFAULT_BROADCASTS))
        return channels_for(match["league"], rules)

    def _build(self, now: datetime) -> dict[str, Any]:
        matches = []
        for match in sorted(self._matches.values(), key=lambda m: m["date"] or ""):
            if self.team_id not in (match["home"]["id"], match["away"]["id"]):
                continue
            us, them = self._sides(match)
            item = dict(match)
            item["home"] = {k: match["home"][k] for k in _MATCH_TEAM_KEYS}
            item["away"] = {k: match["away"][k] for k in _MATCH_TEAM_KEYS}
            item["is_home"] = match["home"]["id"] == self.team_id
            item["tv_de"] = self._channels(match)
            item["result"] = result_for(us, them) if match["state"] == "post" else None
            matches.append(item)
        years_back = int(self._options.get(CONF_HISTORY_YEARS, DEFAULT_HISTORY_YEARS))
        _number_rounds(matches, first_year=now.year - years_back + 1)

        live = [m for m in matches if m["state"] == "in"]
        upcoming = [m for m in matches if m["state"] == "pre"]
        past = [m for m in matches if m["state"] == "post"]
        nxt = upcoming[0] if upcoming else None
        last = past[-1] if past else None

        focus_ids = {m["id"] for m in live} | {m["id"] for m in (nxt, last) if m}
        return {
            "team": self._team_info,
            "matches": matches,
            "live": live,
            "next": nxt,
            "last": last,
            "timelines": {k: v for k, v in self._timelines.items() if k in focus_ids and v},
            "lineups": {k: v for k, v in self._lineups.items() if k in focus_ids},
            "standings": self._standings,
            "league_logos": {k: v for k, v in self._league_logos.items() if v},
            "updated": now.isoformat(),
        }


def _number_rounds(matches: list[dict], first_year: int) -> None:
    """Add matchday numbers (league formats) and legs (two-legged knockout ties).

    ESPN has no matchday field; a club plays once per matchday, so the order of
    its own matches within a competition and season is the matchday. Seasons
    that started before the first fetched calendar year are incomplete, so they
    get no matchday numbers.
    """
    groups: dict[tuple, list[dict]] = {}
    for m in matches:
        groups.setdefault((m["league_id"], m["season"], m["round"]), []).append(m)
    for (_, season, round_name), items in groups.items():
        complete = season is None or season >= first_year
        # A single match without a round (e.g. Supercup) is a one-off, not a matchday.
        league_format = len(items) > 2 and (
            round_name is None
            or any(word in round_name.lower() for word in ("league phase", "group", "regular"))
        )
        for i, m in enumerate(items):
            m["matchday"] = i + 1 if league_format and complete else None
            m["leg"] = i + 1 if not league_format and len(items) == 2 else None


def _key(event: dict) -> tuple:
    return (event["kind"], event["team_id"], event["player"], event["minute"])


def _parse_dt(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None
