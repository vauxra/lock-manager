from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from custom_components.zigbee_lock_manager.const import ValidationError
from custom_components.zigbee_lock_manager.manager import ZigbeeLockManager
from custom_components.zigbee_lock_manager.storage import (
    LockRegistryStore,
    MemoryStoreBackend,
)

from .conftest import FakeHass, make_manager, run


def test_set_code_calls_zha_with_user_code_and_stores_no_public_plaintext() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.set_code(
            "lock.front_door",
            1,
            "123456",
            name="Micheal",
            labels=["household"],
        )
        assert hass.services.calls == [
            (
                "zha",
                "set_lock_user_code",
                {"entity_id": "lock.front_door", "code_slot": 1, "user_code": "123456"},
                True,
            )
        ]
        assert "123456" not in str(manager.registry.public_registry)
        assert (
            manager.registry.private_codes["codes"]["lock.front_door"]["1"]
            == "123456"
        )

    run(scenario())


def test_clear_enable_disable_payloads_do_not_include_code() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.clear_code("lock.front_door", 1)
        await manager.enable_code("lock.front_door", 2)
        await manager.disable_code("lock.front_door", 3)
        payloads = [call[2] for call in hass.services.calls]
        assert payloads == [
            {"entity_id": "lock.front_door", "code_slot": 1},
            {"entity_id": "lock.front_door", "code_slot": 2},
            {"entity_id": "lock.front_door", "code_slot": 3},
        ]
        assert all(
            "user_code" not in payload and "code" not in payload
            for payload in payloads
        )

    run(scenario())


def test_validation_failure_does_not_call_zha() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        with pytest.raises(ValidationError):
            await manager.set_code("lock.front_door", 1, "abcd", name="Bad")
        assert hass.services.calls == []
        assert manager.registry.public_registry["locks"] == {}

    run(scenario())


def test_zha_failure_records_sanitized_failure_without_success_or_public_pin() -> None:
    async def scenario() -> None:
        hass = FakeHass()
        registry = LockRegistryStore(MemoryStoreBackend(), MemoryStoreBackend())
        await registry.async_load()
        manager = ZigbeeLockManager(hass, registry)
        hass.services.raise_on_call = RuntimeError("device rejected user code 123456")
        with pytest.raises(RuntimeError):
            await manager.set_code("lock.front_door", 1, "123456", name="Micheal")
        public = manager.registry.public_registry
        slot = public["locks"]["lock.front_door"]["slots"]["1"]
        assert slot["last_operation"]["status"] == "failed"
        assert "success" not in str(slot["last_operation"])
        assert "123456" not in str(public)
        assert (
            manager.registry.private_codes["codes"]["lock.front_door"]["1"]
            == "123456"
        )

    run(scenario())


def test_apply_registry_uses_private_code_only_for_zha_payload() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=1, name="Guest", code="876543"
        )
        hass.services.calls.clear()
        result = await manager.apply_registry()
        assert result == [
            {
                "entity_id": "lock.front_door",
                "slot": 1,
                "name": "Guest",
                "status": "success",
            }
        ]
        assert hass.services.calls[0][2]["user_code"] == "876543"
        assert "876543" not in str(manager.registry.public_registry)

    run(scenario())


def test_probe_slots_safe_stub_never_blocks() -> None:
    async def scenario() -> None:
        _hass, manager = await make_manager()
        result = await manager.probe_slots("lock.front_door", start_slot=1, end_slot=30)
        assert result["supported"] is False
        assert "code" not in str(result).lower()

    run(scenario())


def test_set_code_disabled_immediately_disables_physical_slot() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.set_code(
            "lock.front_door",
            4,
            "456789",
            name="Disabled Guest",
            enabled=False,
        )
        assert [call[1] for call in hass.services.calls] == [
            "disable_lock_user_code",
        ]
        assert hass.services.calls[0][2] == {
            "entity_id": "lock.front_door",
            "code_slot": 4,
        }
        assert "456789" not in str(manager.registry.public_registry)

    run(scenario())


def test_set_code_future_or_expired_schedule_disables_physical_slot() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        future = datetime.now(UTC) + timedelta(days=1)
        await manager.set_code(
            "lock.front_door",
            5,
            "567890",
            name="Future Guest",
            starts_at=future,
        )
        assert [call[1] for call in hass.services.calls] == [
            "disable_lock_user_code",
        ]

    run(scenario())


def test_apply_registry_records_sanitized_failure() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=6, name="Guest", code="654321"
        )
        hass.services.calls.clear()
        hass.services.raise_on_call = RuntimeError("failed to set 654321")
        result = await manager.apply_registry()
        assert result == [
            {
                "entity_id": "lock.front_door",
                "slot": 6,
                "name": "Guest",
                "status": "failed",
            }
        ]
        public = manager.registry.public_registry
        assert "654321" not in str(public)
        slot = public["locks"]["lock.front_door"]["slots"]["6"]
        assert slot["last_operation"]["status"] == "failed"

    run(scenario())


def test_apply_registry_does_not_program_expired_or_disabled_codes() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        past = datetime.now(UTC) - timedelta(days=1)
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=7,
            name="Expired",
            code="765432",
            expires_at=past,
        )
        hass.services.calls.clear()
        result = await manager.apply_registry()
        assert result == [
            {
                "entity_id": "lock.front_door",
                "slot": 7,
                "name": "Expired",
                "status": "disabled_expired",
            }
        ]
        assert [call[1] for call in hass.services.calls] == ["disable_lock_user_code"]
        assert "765432" not in str(manager.registry.public_registry)

    run(scenario())


def test_clear_all_codes_clears_configured_slot_range_and_registry() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=2, name="Guest", code="2222"
        )
        hass.services.calls.clear()

        result = await manager.clear_all_codes(
            "lock.front_door", start_slot=1, end_slot=3
        )

        assert result == [
            {"entity_id": "lock.front_door", "slot": 1, "status": "success"},
            {"entity_id": "lock.front_door", "slot": 2, "status": "success"},
            {"entity_id": "lock.front_door", "slot": 3, "status": "success"},
        ]
        assert [call[2] for call in hass.services.calls] == [
            {"entity_id": "lock.front_door", "code_slot": 1},
            {"entity_id": "lock.front_door", "code_slot": 2},
            {"entity_id": "lock.front_door", "code_slot": 3},
        ]
        assert manager.registry.safe_summary()["occupied_slot_count"] == 0

    run(scenario())


def test_clear_all_codes_known_only_limits_to_managed_slots() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=4, name="Guest", code="4444"
        )
        hass.services.calls.clear()

        result = await manager.clear_all_codes("lock.front_door", known_only=True)

        assert result == [
            {"entity_id": "lock.front_door", "slot": 4, "status": "success"},
        ]
        assert [call[2] for call in hass.services.calls] == [
            {"entity_id": "lock.front_door", "code_slot": 4},
        ]

    run(scenario())
