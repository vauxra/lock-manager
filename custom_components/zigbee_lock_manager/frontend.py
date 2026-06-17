"""Frontend panel and websocket support for Zigbee Lock Manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .const import DOMAIN, MANAGER_DATA_KEY, validate_entity_id, validate_slot

PANEL_URL_PATH = "zigbee-lock-manager"
PANEL_WEB_COMPONENT = "zigbee-lock-manager-panel"
PANEL_TITLE = "Lock Codes"
PANEL_ICON = "mdi:lock-smart"
STATIC_URL_PATH = f"/{DOMAIN}_static"
STATIC_DIR = Path(__file__).parent / "frontend"
PANEL_MODULE_URL = f"{STATIC_URL_PATH}/lock-manager-panel.js"
STATIC_REGISTERED = "frontend_static_registered"
PANEL_REGISTERED = "frontend_panel_registered"
WEBSOCKET_REGISTERED = "websocket_registered"


def build_ui_summary(
    manager: Any, configured_locks: list[str] | None = None
) -> dict[str, Any]:
    """Return PIN-free UI data for the panel."""
    summary = manager.registry.safe_summary()
    lock_entities = sorted(
        {
            *(configured_locks or []),
            *summary.get("locks", {}).keys(),
        }
    )
    return {
        **summary,
        "lock_entities": lock_entities,
        "bounds": {
            "min_slot": manager.min_slot,
            "max_slot": manager.max_slot,
            "min_code_length": manager.min_code_length,
            "max_code_length": manager.max_code_length,
        },
    }


async def build_private_code_response(
    manager: Any, entity_id: str, slot: int
) -> dict[str, str | None]:
    """Return a private PIN for an explicit admin reveal action."""
    entity_id = validate_entity_id(entity_id)
    slot = validate_slot(slot, minimum=manager.min_slot, maximum=manager.max_slot)
    return {"code": await manager.registry.async_get_private_code(entity_id, slot)}


def _configured_lock_entities(hass: Any) -> list[str]:
    """Return lock entities configured on all entries."""
    locks: set[str] = set()
    config_entries = getattr(hass, "config_entries", None)
    if config_entries is None or not hasattr(config_entries, "async_entries"):
        return []
    for entry in config_entries.async_entries(DOMAIN):
        data = dict(getattr(entry, "data", {}) or {})
        data.update(dict(getattr(entry, "options", {}) or {}))
        for entity_id in data.get("lock_entities", []) or []:
            if isinstance(entity_id, str):
                locks.add(entity_id)
    return sorted(locks)


def _current_manager(hass: Any) -> Any:
    manager = hass.data.get(DOMAIN, {}).get(MANAGER_DATA_KEY)
    if manager is None:
        raise RuntimeError("Zigbee Lock Manager is not loaded")
    return manager


async def async_setup_frontend(hass: Any) -> None:
    """Register the sidebar panel and websocket API."""
    data = hass.data.setdefault(DOMAIN, {})
    await _async_register_static_and_panel(hass, data)
    _async_register_websocket_api(hass, data)


async def _async_register_static_and_panel(hass: Any, data: dict[str, Any]) -> None:
    """Serve the panel JS and register a sidebar panel once."""
    from homeassistant.components import (  # type: ignore[import-not-found]
        frontend,
        panel_custom,
    )
    from homeassistant.components.http import (
        StaticPathConfig,  # type: ignore[import-not-found]
    )

    if not data.get(STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, str(STATIC_DIR), cache_headers=False)]
        )
        data[STATIC_REGISTERED] = True

    if not data.get(PANEL_REGISTERED) and PANEL_URL_PATH not in hass.data.get(
        frontend.DATA_PANELS, {}
    ):
        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_WEB_COMPONENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=PANEL_MODULE_URL,
            embed_iframe=False,
            require_admin=True,
            config={"domain": DOMAIN},
            config_panel_domain=DOMAIN,
        )
        data[PANEL_REGISTERED] = True


def _async_register_websocket_api(hass: Any, data: dict[str, Any]) -> None:
    """Register websocket commands once per HA runtime."""
    if data.get(WEBSOCKET_REGISTERED):
        return

    import voluptuous as vol  # type: ignore[import-not-found]
    from homeassistant.components import websocket_api  # type: ignore[import-not-found]
    from homeassistant.core import callback  # type: ignore[import-not-found]

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/summary"})
    @websocket_api.require_admin
    @callback
    def websocket_summary(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
        """Return PIN-free registry data for the panel."""
        manager = _current_manager(hass)
        connection.send_result(
            msg["id"],
            build_ui_summary(manager, _configured_lock_entities(hass)),
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/private_code",
            vol.Required("entity_id"): str,
            vol.Required("slot"): vol.Coerce(int),
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def websocket_private_code(
        hass: Any, connection: Any, msg: dict[str, Any]
    ) -> None:
        """Return a private PIN only after an explicit admin reveal request."""
        manager = _current_manager(hass)
        connection.send_result(
            msg["id"],
            await build_private_code_response(manager, msg["entity_id"], msg["slot"]),
        )

    websocket_api.async_register_command(hass, websocket_summary)
    websocket_api.async_register_command(hass, websocket_private_code)
    data[WEBSOCKET_REGISTERED] = True


def async_remove_frontend_panel(hass: Any) -> None:
    """Remove the sidebar panel after the last config entry unloads."""
    try:
        from homeassistant.components import frontend  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - HA runtime only
        return
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    hass.data.get(DOMAIN, {}).pop(PANEL_REGISTERED, None)
