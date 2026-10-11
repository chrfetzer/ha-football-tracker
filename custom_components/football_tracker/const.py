"""Constants for the Football Tracker integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "football_tracker"
LOGGER = logging.getLogger(__package__)
VERSION = "0.1.0"

CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"
CONF_TEAM_QUERY = "team_query"
CONF_HISTORY_YEARS = "history_years"
CONF_BROADCASTS = "broadcasts"
CONF_KICKOFF_NOTICE = "kickoff_notice_minutes"
CONF_INCLUDE_FRIENDLIES = "include_friendlies"

DEFAULT_TEAM_QUERY = "Bayern"
DEFAULT_HISTORY_YEARS = 1
DEFAULT_KICKOFF_NOTICE = 30
# One rule per line: "<part of competition name> = <channels>". "*" is the fallback.
DEFAULT_BROADCASTS = """Bundesliga = Sky, DAZN
Champions League = DAZN, Prime Video
DFB-Pokal = Sky, ARD/ZDF
Supercup = Sat.1, Sky
Club World Cup = DAZN"""

FRIENDLY_LEAGUES = {"club.friendly"}

# ESPN competition names -> short names used everywhere else.
LEAGUE_NAMES = {
    "German Bundesliga": "Bundesliga",
    "German 2. Bundesliga": "2. Bundesliga",
    "UEFA Champions League": "Champions League",
    "UEFA Europa League": "Europa League",
    "UEFA Europa Conference League": "Conference League",
    "UEFA Conference League": "Conference League",
    "German Cup": "DFB-Pokal",
    "German DFB Pokal": "DFB-Pokal",
    "German Super Cup": "Supercup",
    "German Supercup": "Supercup",
    "German DFL-Supercup": "Supercup",
    "UEFA Super Cup": "UEFA Super Cup",
    "FIFA Club World Cup": "Club World Cup",
    "Club Friendly": "Friendly",
}

# Polling cadence
INTERVAL_LIVE = timedelta(seconds=20)
INTERVAL_SOON = timedelta(minutes=5)
INTERVAL_IDLE = timedelta(minutes=30)
INDEX_MAX_AGE = timedelta(hours=6)
STANDINGS_MAX_AGE = timedelta(hours=3)
UPCOMING_MAX_AGE = timedelta(hours=6)
UPCOMING_NEAR_MAX_AGE = timedelta(minutes=30)
LIVE_WINDOW_BEFORE = timedelta(minutes=20)
# Covers extra time and penalties; a match still not final after this is left alone.
LIVE_WINDOW_AFTER = timedelta(hours=4)

EVENT_TYPE = f"{DOMAIN}_event"

CARD_URL = f"/{DOMAIN}/football-tracker-card.js"
