"""Diagnostics for Zigbee Lock Manager."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN, MANAGER_DATA_KEY, redact_data


async def async_get_config_entry_diagnostics(hass: Any, entry: Any) -> dict[str, Any]:
    """Return diagnostics with no plaintext PINs or private store contents."""
    manager = hass.data[DOMAIN][entry.entry_id][MANAGER_DATA_KEY]
    return redact_data(
        {
            "entry": {
                "entry_id": getattr(entry, "entry_id", None),
                "title": getattr(entry, "title", None),
                "data": getattr(entry, "data", {}),
                "options": getattr(entry, "options", {}),
            },
            "registry_summary": manager.registry.safe_summary(),
        }
    )
