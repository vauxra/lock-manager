from __future__ import annotations

from types import SimpleNamespace

from custom_components.zigbee_lock_manager import _entry_runtime_options
from custom_components.zigbee_lock_manager.config_flow import (
    CONF_LOCK_ENTITIES,
    CONF_MAX_CODE_LENGTH,
    CONF_MAX_SLOT,
    CONF_MIN_CODE_LENGTH,
    CONF_MIN_SLOT,
    ZigbeeLockManagerConfigFlow,
    ZigbeeLockManagerOptionsFlow,
    _validate_user_input,
)

from .conftest import run


def test_validate_user_input_allows_empty_initial_locks() -> None:
    data = _validate_user_input({})
    assert data[CONF_LOCK_ENTITIES] == []
    assert data[CONF_MIN_SLOT] == 1
    assert data[CONF_MAX_SLOT] == 30
    assert data[CONF_MIN_CODE_LENGTH] == 4
    assert data[CONF_MAX_CODE_LENGTH] == 8


def test_validate_user_input_normalizes_single_lock() -> None:
    data = _validate_user_input({CONF_LOCK_ENTITIES: "lock.front_door"})
    assert data[CONF_LOCK_ENTITIES] == ["lock.front_door"]


def test_validate_user_input_rejects_bad_ranges() -> None:
    for bad in [
        {CONF_MIN_SLOT: 5, CONF_MAX_SLOT: 4},
        {CONF_MIN_CODE_LENGTH: 9, CONF_MAX_CODE_LENGTH: 8},
    ]:
        try:
            _validate_user_input(bad)
        except Exception:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected validation failure")


def test_config_flow_fallback_create_entry() -> None:
    async def scenario() -> None:
        flow = ZigbeeLockManagerConfigFlow()
        result = await flow.async_step_user(
            {
                CONF_LOCK_ENTITIES: ["lock.front_door"],
                CONF_MIN_SLOT: 1,
                CONF_MAX_SLOT: 30,
                CONF_MIN_CODE_LENGTH: 4,
                CONF_MAX_CODE_LENGTH: 8,
            }
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Zigbee Lock Manager"
        assert result["data"][CONF_LOCK_ENTITIES] == ["lock.front_door"]

    run(scenario())


def test_config_flow_fallback_form_on_invalid_input() -> None:
    async def scenario() -> None:
        flow = ZigbeeLockManagerConfigFlow()
        result = await flow.async_step_user({CONF_MIN_SLOT: 30, CONF_MAX_SLOT: 1})
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_input"

    run(scenario())


def test_entry_runtime_options_merge_config_and_options() -> None:
    entry = SimpleNamespace(
        data={
            CONF_MIN_SLOT: 2,
            CONF_MAX_SLOT: 40,
            CONF_MIN_CODE_LENGTH: 4,
            CONF_MAX_CODE_LENGTH: 8,
        },
        options={CONF_MAX_SLOT: 12, CONF_MAX_CODE_LENGTH: 6},
    )
    assert _entry_runtime_options(entry) == {
        "min_slot": 2,
        "max_slot": 12,
        "min_code_length": 4,
        "max_code_length": 6,
    }


def test_options_flow_uses_private_config_entry_reference() -> None:
    async def scenario() -> None:
        entry = SimpleNamespace(
            data={CONF_LOCK_ENTITIES: ["lock.front_door"]},
            options={CONF_MAX_SLOT: 12},
        )
        flow = ZigbeeLockManagerOptionsFlow(entry)
        result = await flow.async_step_init()
        assert result["type"] == "form"

    run(scenario())
