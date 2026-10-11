"""Base entity for Football Tracker."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FootballCoordinator


class FootballEntity(CoordinatorEntity[FootballCoordinator]):
    """Common device and naming for all entities of one tracked team."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by ESPN"

    def __init__(self, coordinator: FootballCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.team_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.team_id)},
            name=coordinator.team_name,
            manufacturer="ESPN",
            model="Football club",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://www.espn.com/soccer/club/_/id/{coordinator.team_id}",
        )


def match_summary(match: dict | None) -> dict:
    """Small, flat attribute set for automations and simple cards."""
    if not match:
        return {}
    home, away = match["home"], match["away"]
    us, them = (home, away) if match["is_home"] else (away, home)
    return {
        "match_id": match["id"],
        "competition": match["league"],
        "round": match["round"],
        "matchday": match.get("matchday"),
        "kickoff": match["date"],
        "home": home["name"],
        "away": away["name"],
        "home_score": home["score"],
        "away_score": away["score"],
        "opponent": them["name"],
        "opponent_logo": them["logo"],
        "team_score": us["score"],
        "opponent_score": them["score"],
        "team_shootout": us["shootout"],
        "opponent_shootout": them["shootout"],
        "venue": match["venue"],
        "city": match["city"],
        "status": match["status_detail"],
        "clock": match["clock"],
        "tv": match["tv_de"],
        "result": match["result"],
        "url": match["url"],
    }
