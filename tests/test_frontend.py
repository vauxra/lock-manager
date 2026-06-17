from __future__ import annotations

from custom_components.zigbee_lock_manager.frontend import (
    _configured_lock_entities,
    build_private_code_response,
    build_ui_summary,
)

from .conftest import fake_entry, make_manager, run


def test_ui_summary_includes_configured_and_registry_locks_without_pins() -> None:
    async def scenario() -> None:
        _hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=12,
            name="Guest 123456",
            code="123456",
            labels=["123456", "guest"],
        )

        summary = build_ui_summary(manager, ["lock.back_door"])

        assert summary["lock_entities"] == ["lock.back_door", "lock.front_door"]
        assert summary["bounds"] == {
            "min_slot": 1,
            "max_slot": 30,
            "min_code_length": 4,
            "max_code_length": 8,
        }
        assert summary["occupied_slot_count"] == 1
        assert "123456" not in str(summary)
        slot = summary["locks"]["lock.front_door"]["slots"]["12"]
        assert slot["has_private_code"] is True
        assert slot["code_length"] == 6

    run(scenario())


def test_configured_lock_entities_reads_entry_data_and_options() -> None:
    async def scenario() -> None:
        hass, _manager = await make_manager()
        hass.config_entries.entries = [
            fake_entry(data={"lock_entities": ["lock.front_door"]}),
            fake_entry(
                options={"lock_entities": ["lock.back_door", "lock.front_door"]}
            ),
        ]

        assert _configured_lock_entities(hass) == [
            "lock.back_door",
            "lock.front_door",
        ]

    run(scenario())


def test_private_code_response_requires_explicit_lookup() -> None:
    async def scenario() -> None:
        _hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=2,
            name="Guest",
            code="246810",
        )

        summary = build_ui_summary(manager)
        assert "246810" not in str(summary)

        response = await build_private_code_response(manager, "lock.front_door", 2)
        assert response == {"code": "246810"}

    run(scenario())
