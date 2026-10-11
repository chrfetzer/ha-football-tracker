"""Live-match binary sensor for Football Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FootballConfigEntry
from .entity import FootballEntity, match_summary


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FootballConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LiveBinarySensor(entry.runtime_data, "live")])


class LiveBinarySensor(FootballEntity, BinarySensorEntity):
    """On while the team is playing."""

    _attr_icon = "mdi:broadcast"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["live"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        live = self.coordinator.data["live"]
        return match_summary(live[0]) if live else {}
