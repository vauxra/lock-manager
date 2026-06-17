"""Zigbee Lock Manager Home Assistant custom integration."""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_MAX_CODE_LENGTH,
    CONF_MAX_SLOT,
    CONF_MIN_CODE_LENGTH,
    CONF_MIN_SLOT,
    DEFAULT_MAX_CODE_LENGTH,
    DEFAULT_MAX_SLOT,
    DEFAULT_MIN_CODE_LENGTH,
    DEFAULT_MIN_SLOT,
    DOMAIN,
    MANAGER_DATA_KEY,
    PLATFORMS,
    PUBLIC_SERVICE_NAMES,
    SERVICE_APPLY_REGISTRY,
    SERVICE_APPLY_SCHEDULES,
    SERVICE_CLEAR_CODE,
    SERVICE_DISABLE_CODE,
    SERVICE_ENABLE_CODE,
    SERVICE_PROBE_SLOTS,
    SERVICE_SET_CODE,
    SERVICE_SYNC_REGISTRY,
)
from .manager import ZigbeeLockManager
from .storage import LockRegistryStore


def _service_schema(service_name: str) -> Any:
    """Build a HA service schema when voluptuous is available."""
    try:
        import voluptuous as vol  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - used only in lightweight tests
        return None

    entity = {vol.Required("entity_id"): str}
    slot = {vol.Required("slot"): vol.Coerce(int)}
    optional_entity = {vol.Optional("entity_id"): str}
    if service_name == SERVICE_SET_CODE:
        return vol.Schema(
            {
                **entity,
                **slot,
                vol.Required("name"): str,
                vol.Required("code"): str,
                vol.Optional("labels"): object,
                vol.Optional("enabled", default=True): bool,
                vol.Optional("starts_at"): object,
                vol.Optional("expires_at"): object,
                vol.Optional("schedule"): object,
                vol.Optional("notes"): str,
            }
        )
    if service_name in {SERVICE_CLEAR_CODE, SERVICE_ENABLE_CODE, SERVICE_DISABLE_CODE}:
        return vol.Schema({**entity, **slot})
    if service_name in {
        SERVICE_SYNC_REGISTRY,
        SERVICE_APPLY_REGISTRY,
        SERVICE_APPLY_SCHEDULES,
    }:
        return vol.Schema(optional_entity)
    if service_name == SERVICE_PROBE_SLOTS:
        return vol.Schema(
            {
                **optional_entity,
                vol.Optional("start_slot"): vol.Coerce(int),
                vol.Optional("end_slot"): vol.Coerce(int),
            }
        )
    return None


async def async_setup(_hass: Any, _config: dict[str, Any]) -> bool:
    """YAML setup hook; config flow is the supported path."""
    return True


def _entry_runtime_options(entry: Any) -> dict[str, int]:
    """Return merged config-entry/options validation bounds."""
    data = dict(getattr(entry, "data", {}) or {})
    data.update(dict(getattr(entry, "options", {}) or {}))
    return {
        "min_slot": int(data.get(CONF_MIN_SLOT, DEFAULT_MIN_SLOT)),
        "max_slot": int(data.get(CONF_MAX_SLOT, DEFAULT_MAX_SLOT)),
        "min_code_length": int(
            data.get(CONF_MIN_CODE_LENGTH, DEFAULT_MIN_CODE_LENGTH)
        ),
        "max_code_length": int(
            data.get(CONF_MAX_CODE_LENGTH, DEFAULT_MAX_CODE_LENGTH)
        ),
    }


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up Zigbee Lock Manager from a config entry."""
    options = _entry_runtime_options(entry)
    registry = await LockRegistryStore.from_hass(hass, **options)
    manager = ZigbeeLockManager(hass, registry, **options)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {MANAGER_DATA_KEY: manager}
    hass.data[DOMAIN][MANAGER_DATA_KEY] = manager

    await _async_register_services(hass)
    await manager.apply_schedules()
    await manager.scheduler.async_schedule_timers()

    if hasattr(hass.config_entries, "async_forward_entry_setups"):
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    elif hasattr(hass.config_entries, "async_forward_entry_setup"):
        for platform in PLATFORMS:
            await hass.config_entries.async_forward_entry_setup(entry, platform)
    return True


async def _async_register_services(hass: Any) -> None:
    """Register public service-first actions once per HA instance."""
    registered = hass.data.setdefault(DOMAIN, {}).setdefault(
        "registered_services", set()
    )

    async def _handle(call: Any) -> Any:
        data = dict(getattr(call, "data", {}) or {})
        manager = hass.data.get(DOMAIN, {}).get(MANAGER_DATA_KEY)
        if manager is None:
            raise RuntimeError("Zigbee Lock Manager is not loaded")
        return await manager.handle_service_call(call.service, data)

    for service in PUBLIC_SERVICE_NAMES:
        if service in registered:
            continue
        hass.services.async_register(
            DOMAIN,
            service,
            _handle,
            schema=_service_schema(service),
        )
        registered.add(service)


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload the integration config entry."""
    unload_ok = True
    if hasattr(hass.config_entries, "async_unload_platforms"):
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.pop(entry.entry_id, None)
        if isinstance(entry_data, dict):
            manager = entry_data.get(MANAGER_DATA_KEY)
            if manager is not None:
                manager.scheduler.async_cancel_timers()
        if not any(isinstance(value, dict) for value in domain_data.values()):
            domain_data.pop(MANAGER_DATA_KEY, None)
    return unload_ok
