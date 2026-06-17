from __future__ import annotations

from types import SimpleNamespace

import pytest
from custom_components.zigbee_lock_manager import (
    _async_register_services,
    _async_update_listener,
    async_unload_entry,
)
from custom_components.zigbee_lock_manager.const import (
    DOMAIN,
    MANAGER_DATA_KEY,
    PUBLIC_SERVICE_NAMES,
    SERVICE_DISABLE_CODE,
)

from .conftest import fake_entry, make_manager, run


def _install_manager(hass, manager, entry_id: str = "entry-1") -> None:
    hass.data.setdefault(DOMAIN, {})[entry_id] = {MANAGER_DATA_KEY: manager}
    hass.data[DOMAIN][MANAGER_DATA_KEY] = manager


def test_services_registered_once_even_across_reloads() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        _install_manager(hass, manager)
        await _async_register_services(hass)
        await _async_register_services(hass)
        for service in PUBLIC_SERVICE_NAMES:
            assert (DOMAIN, service) in hass.services.registered
        # The guard set prevents duplicate registration on reload.
        assert hass.services.register_calls == len(PUBLIC_SERVICE_NAMES)

    run(scenario())


def test_service_handler_dispatches_to_current_manager_instance() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        _install_manager(hass, manager)
        await _async_register_services(hass)
        handler = hass.services.registered[(DOMAIN, SERVICE_DISABLE_CODE)][0]

        call = SimpleNamespace(
            service=SERVICE_DISABLE_CODE,
            data={"entity_id": "lock.front_door", "slot": 1},
        )
        await handler(call)
        assert hass.services.calls[-1][:3] == (
            "zha",
            "disable_lock_user_code",
            {"entity_id": "lock.front_door", "code_slot": 1},
        )

        # Simulate a reload swapping in a new manager bound to a new hass.
        hass2, manager2 = await make_manager()
        hass.data[DOMAIN][MANAGER_DATA_KEY] = manager2
        before = len(hass.services.calls)
        await handler(call)
        # The new manager (and its hass) handled the call, not the stale one.
        assert len(hass.services.calls) == before
        assert hass2.services.calls[-1][:2] == ("zha", "disable_lock_user_code")

    run(scenario())


def test_service_handler_raises_when_no_manager_loaded() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        _install_manager(hass, manager)
        await _async_register_services(hass)
        handler = hass.services.registered[(DOMAIN, SERVICE_DISABLE_CODE)][0]
        hass.data[DOMAIN].pop(MANAGER_DATA_KEY)
        with pytest.raises(RuntimeError):
            await handler(
                SimpleNamespace(
                    service=SERVICE_DISABLE_CODE,
                    data={"entity_id": "lock.front_door", "slot": 1},
                )
            )

    run(scenario())


def test_unload_cancels_timers_and_clears_manager_but_keeps_services() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        _install_manager(hass, manager)
        await _async_register_services(hass)

        cancelled = {"value": False}
        manager.scheduler.async_cancel_timers = lambda: cancelled.update(value=True)

        entry = fake_entry()
        assert await async_unload_entry(hass, entry) is True
        assert cancelled["value"] is True
        assert entry.entry_id not in hass.data[DOMAIN]
        assert MANAGER_DATA_KEY not in hass.data[DOMAIN]
        # Registered service handlers persist so a later reload reuses them.
        assert "registered_services" in hass.data[DOMAIN]

    run(scenario())


def test_update_listener_reloads_entry_to_apply_option_changes() -> None:
    async def scenario() -> None:
        hass, _manager = await make_manager()
        entry = fake_entry(entry_id="entry-reload")
        await _async_update_listener(hass, entry)
        assert hass.config_entries.reloaded_entry_ids == ["entry-reload"]

    run(scenario())
