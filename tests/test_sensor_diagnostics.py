from __future__ import annotations

from custom_components.zigbee_lock_manager.const import DOMAIN, MANAGER_DATA_KEY
from custom_components.zigbee_lock_manager.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.zigbee_lock_manager.sensor import ZigbeeLockManagerSummarySensor

from .conftest import fake_entry, make_manager, run


def test_sensor_attributes_do_not_expose_plaintext_pin_or_fingerprint() -> None:
    async def scenario() -> None:
        _hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=1, name="Guest", code="123456"
        )
        sensor = ZigbeeLockManagerSummarySensor(manager, "entry-1")
        attrs = sensor.extra_state_attributes
        assert sensor.native_value == 1
        assert "123456" not in str(attrs)
        assert "code_fingerprint" not in str(attrs)

    run(scenario())


def test_diagnostics_redact_config_data_and_exclude_private_store() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=1, name="Guest", code="123456"
        )
        entry = fake_entry(data={"user_code": "123456"})
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {MANAGER_DATA_KEY: manager}
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert "123456" not in str(diag)
        assert "private_codes" not in str(diag)
        assert "codes" not in str(diag)
        assert diag["registry_summary"]["occupied_slot_count"] == 1

    run(scenario())
