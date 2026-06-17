"""Safe summary sensor for Zigbee Lock Manager."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN, MANAGER_DATA_KEY

try:  # pragma: no cover - HA runtime import
    from homeassistant.components.sensor import (
        SensorEntity,  # type: ignore[import-not-found]
    )
except Exception:  # pragma: no cover - lightweight tests

    class SensorEntity:  # type: ignore[no-redef]
        """Fallback base for tests without Home Assistant installed."""


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Set up the safe registry summary sensor."""
    manager = hass.data[DOMAIN][entry.entry_id][MANAGER_DATA_KEY]
    async_add_entities([ZigbeeLockManagerSummarySensor(manager, entry.entry_id)])


class ZigbeeLockManagerSummarySensor(SensorEntity):
    """Sensor exposing counts and redacted metadata only."""

    _attr_has_entity_name = True
    _attr_name = "Registry Summary"
    _attr_icon = "mdi:lock-smart"

    def __init__(self, manager: Any, entry_id: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_registry_summary"

    @property
    def native_value(self) -> int:
        """Return occupied slot count."""
        return int(self.manager.registry.safe_summary()["occupied_slot_count"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return PIN-free registry attributes."""
        return self.manager.registry.safe_summary()
