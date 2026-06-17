from __future__ import annotations

from custom_components.zigbee_lock_manager.const import (
    METADATA_STORE_KEY,
    PRIVATE_CODE_STORE_KEY,
)
from custom_components.zigbee_lock_manager.storage import (
    LockRegistryStore,
    MemoryStoreBackend,
)

from .conftest import run


def test_private_code_store_is_separate_from_metadata_store() -> None:
    metadata = MemoryStoreBackend()
    private = MemoryStoreBackend()
    registry = LockRegistryStore(metadata, private)
    assert registry.metadata_store is metadata
    assert registry.private_code_store is private
    assert registry.metadata_store_key == METADATA_STORE_KEY
    assert registry.private_code_store_key == PRIVATE_CODE_STORE_KEY
    assert registry.metadata_store_key != registry.private_code_store_key


def test_reject_same_store_for_public_and_private_data() -> None:
    store = MemoryStoreBackend()
    try:
        LockRegistryStore(store, store)
    except ValueError as err:
        assert "separate" in str(err)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_set_code_metadata_keeps_plaintext_only_in_private_store() -> None:
    async def scenario() -> None:
        metadata = MemoryStoreBackend()
        private = MemoryStoreBackend()
        registry = LockRegistryStore(metadata, private)
        await registry.async_load()
        await registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=1,
            name="Micheal",
            code="123456",
            labels=["household"],
            enabled=True,
        )

        public = registry.public_registry
        assert "123456" not in str(public)
        assert public["locks"]["lock.front_door"]["slots"]["1"]["code_length"] == 6
        slot = public["locks"]["lock.front_door"]["slots"]["1"]
        assert slot["has_private_code"] is True
        assert "code_fingerprint" not in slot
        assert private.data["codes"]["lock.front_door"]["1"] == "123456"
        assert metadata.data is not private.data

    run(scenario())


def test_safe_summary_redacts_pin_and_omits_fingerprint() -> None:
    async def scenario() -> None:
        registry = LockRegistryStore(MemoryStoreBackend(), MemoryStoreBackend())
        await registry.async_load()
        await registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=2,
            name="Guest",
            code="876543",
            labels="guest",
        )
        await registry.async_record_operation(
            entity_id="lock.front_door",
            slot=2,
            operation="set_code",
            status="failed",
            error="device rejected 876543",
            secrets=["876543"],
        )
        summary = registry.safe_summary()
        assert summary["managed_lock_count"] == 1
        assert summary["occupied_slot_count"] == 1
        assert "876543" not in str(summary)
        assert "code_fingerprint" not in str(summary)

    run(scenario())


def test_clear_removes_public_and_private_slot() -> None:
    async def scenario() -> None:
        registry = LockRegistryStore(MemoryStoreBackend(), MemoryStoreBackend())
        await registry.async_load()
        await registry.async_set_code_metadata(
            entity_id="lock.front_door", slot=1, name="A", code="1234"
        )
        await registry.async_remove_code_slot(entity_id="lock.front_door", slot=1)
        assert registry.public_registry["locks"] == {}
        assert registry.private_codes["codes"] == {}

    run(scenario())


def test_public_schedule_and_notes_are_redacted() -> None:
    async def scenario() -> None:
        registry = LockRegistryStore(MemoryStoreBackend(), MemoryStoreBackend())
        await registry.async_load()
        await registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=3,
            name="Guest",
            code="246810",
            schedule={"note": "temporary 246810 access"},
            notes="pin is 246810",
        )
        public = registry.public_registry
        assert "246810" not in str(public)
        slot = public["locks"]["lock.front_door"]["slots"]["3"]
        assert slot["schedule"]["note"] == "temporary [REDACTED] access"
        assert slot["notes"] == "pin is [REDACTED]"

    run(scenario())


def test_public_metadata_redacts_name_labels_and_schedule_keys() -> None:
    async def scenario() -> None:
        registry = LockRegistryStore(MemoryStoreBackend(), MemoryStoreBackend())
        await registry.async_load()
        await registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=4,
            name="Guest 135790",
            labels=["135790", "guest"],
            code="135790",
            schedule={"135790": 135790, "ok": True},
        )
        public = registry.public_registry
        summary = registry.safe_summary()
        assert "135790" not in str(public)
        assert "135790" not in str(summary)

    run(scenario())


def test_normalize_registry_scrubs_legacy_public_pin_fields() -> None:
    async def scenario() -> None:
        metadata = MemoryStoreBackend(
            {
                "version": 1,
                "locks": {
                    "lock.front_door": {
                        "slots": {
                            "1": {
                                "name": "Guest",
                                "code": "123456",
                                "pin": "123456",
                                "code_fingerprint": "sha256:anything",
                                "labels": ["123456"],
                                "schedule": {"123456": "123456"},
                            },
                            "bad-slot": {"code": "999999"},
                        }
                    }
                },
            }
        )
        registry = LockRegistryStore(metadata, MemoryStoreBackend())
        await registry.async_load()
        public = registry.public_registry
        assert "123456" not in str(public)
        assert "999999" not in str(public)
        slot = public["locks"]["lock.front_door"]["slots"]["1"]
        assert "code" not in slot
        assert "pin" not in slot
        assert "code_fingerprint" not in slot

    run(scenario())
