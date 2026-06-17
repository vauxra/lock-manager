"""Private-code and public-metadata storage for Zigbee Lock Manager."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from .const import (
    DEFAULT_MAX_CODE_LENGTH,
    DEFAULT_MAX_SLOT,
    DEFAULT_MIN_CODE_LENGTH,
    DEFAULT_MIN_SLOT,
    METADATA_STORE_KEY,
    PRIVATE_CODE_STORE_KEY,
    STORAGE_VERSION,
    normalize_labels,
    parse_datetime,
    redact_data,
    redact_text,
    validate_code,
    validate_entity_id,
    validate_name,
    validate_slot,
)

PUBLIC_TEXT_LIMIT = 256


def sanitize_public_text(
    value: Any, *, secrets: list[str] | None = None
) -> str | None:
    """Return PIN-redacted, bounded text suitable for public metadata."""
    if value in (None, ""):
        return None
    return redact_text(str(value), secrets=secrets)[:PUBLIC_TEXT_LIMIT]


def sanitize_public_key(value: Any, *, secrets: list[str] | None = None) -> str:
    """Return a redacted string key for public free-form metadata."""
    return sanitize_public_text(value, secrets=secrets) or "[empty]"


def sanitize_public_value(value: Any, *, secrets: list[str] | None = None) -> Any:
    """Recursively sanitize public schedule/notes metadata, including keys."""
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return {
            sanitize_public_key(k, secrets=secrets): sanitize_public_value(
                v, secrets=secrets
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize_public_value(item, secrets=secrets) for item in value]
    if isinstance(value, tuple):
        return [sanitize_public_value(item, secrets=secrets) for item in value]
    if isinstance(value, bool):
        return value
    return sanitize_public_text(value, secrets=secrets)


def sanitize_public_labels(
    labels: Any, *, secrets: list[str] | None = None
) -> list[str]:
    """Normalize and redact labels before public storage."""
    sanitized = [
        label
        for item in normalize_labels(labels)
        if (label := sanitize_public_text(item, secrets=secrets))
    ]
    return sorted(set(sanitized))


class AsyncStoreBackend(Protocol):
    """Small protocol shared by HA Store and test fakes."""

    async def async_load(self) -> dict[str, Any] | None: ...

    async def async_save(self, data: dict[str, Any]) -> None: ...


class MemoryStoreBackend:
    """In-memory async store used by lightweight tests."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self.data = deepcopy(initial)
        self.save_count = 0

    async def async_load(self) -> dict[str, Any] | None:
        return deepcopy(self.data)

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = deepcopy(data)
        self.save_count += 1


def utcnow_iso() -> str:
    """Return a timezone-aware UTC timestamp string."""
    return datetime.now(UTC).isoformat()


def default_registry() -> dict[str, Any]:
    """Return an empty public metadata registry."""
    return {"version": STORAGE_VERSION, "locks": {}}


def default_private_codes() -> dict[str, Any]:
    """Return an empty private code store shape."""
    return {"version": STORAGE_VERSION, "codes": {}}


async def make_ha_store(hass: Any, key: str, *, private: bool = False) -> Any:
    """Create a Home Assistant Store with atomic writes.

    Kept in a helper so unit tests can assert the metadata and private stores are
    separate without importing Home Assistant.
    """
    from homeassistant.helpers.storage import Store  # type: ignore[import-not-found]

    return Store(
        hass,
        STORAGE_VERSION,
        key,
        private=private,
        atomic_writes=True,
    )


class LockRegistryStore:
    """Owns public registry metadata and dedicated private PIN storage."""

    def __init__(
        self,
        metadata_store: AsyncStoreBackend,
        private_code_store: AsyncStoreBackend,
        *,
        min_slot: int = DEFAULT_MIN_SLOT,
        max_slot: int = DEFAULT_MAX_SLOT,
        min_code_length: int = DEFAULT_MIN_CODE_LENGTH,
        max_code_length: int = DEFAULT_MAX_CODE_LENGTH,
    ) -> None:
        if metadata_store is private_code_store:
            raise ValueError("metadata and private code stores must be separate")
        self.metadata_store = metadata_store
        self.private_code_store = private_code_store
        self.metadata_store_key = METADATA_STORE_KEY
        self.private_code_store_key = PRIVATE_CODE_STORE_KEY
        self.min_slot = min_slot
        self.max_slot = max_slot
        self.min_code_length = min_code_length
        self.max_code_length = max_code_length
        self._registry = default_registry()
        self._private_codes = default_private_codes()
        self.loaded = False

    @classmethod
    async def from_hass(
        cls,
        hass: Any,
        *,
        min_slot: int = DEFAULT_MIN_SLOT,
        max_slot: int = DEFAULT_MAX_SLOT,
        min_code_length: int = DEFAULT_MIN_CODE_LENGTH,
        max_code_length: int = DEFAULT_MAX_CODE_LENGTH,
    ) -> LockRegistryStore:
        """Create and load a registry backed by Home Assistant storage."""
        metadata = await make_ha_store(hass, METADATA_STORE_KEY, private=False)
        private = await make_ha_store(hass, PRIVATE_CODE_STORE_KEY, private=True)
        store = cls(
            metadata,
            private,
            min_slot=min_slot,
            max_slot=max_slot,
            min_code_length=min_code_length,
            max_code_length=max_code_length,
        )
        await store.async_load()
        return store

    async def async_load(self) -> None:
        """Load both stores and normalize missing/corrupt top-level keys."""
        registry = await self.metadata_store.async_load()
        codes = await self.private_code_store.async_load()
        self._registry = self._normalize_registry(registry)
        self._private_codes = self._normalize_private_codes(codes)
        self.loaded = True

    async def async_save(self) -> None:
        """Persist metadata and private codes to their separate stores."""
        await self.metadata_store.async_save(self.public_registry)
        await self.private_code_store.async_save(self.private_codes)

    @property
    def public_registry(self) -> dict[str, Any]:
        """Return a deep copy of public metadata only."""
        return deepcopy(self._registry)

    @property
    def private_codes(self) -> dict[str, Any]:
        """Return a deep copy of private code material.

        This property exists for explicit tests/internal workflows only and is
        never used by sensors or diagnostics.
        """
        return deepcopy(self._private_codes)

    def _scrub_slot_metadata(self, slot: int, metadata: Any) -> dict[str, Any]:
        """Remove legacy/public secret fields and sanitize public metadata."""
        if not isinstance(metadata, dict):
            metadata = {}
        scrubbed = deepcopy(metadata)
        for key in (
            "code",
            "pin",
            "user_code",
            "private_code",
            "secret",
            "password",
            "token",
            "code_fingerprint",
        ):
            scrubbed.pop(key, None)
        scrubbed["name"] = sanitize_public_text(
            scrubbed.get("name") or f"Slot {slot}"
        )
        scrubbed["labels"] = sanitize_public_labels(scrubbed.get("labels"))
        scrubbed["schedule"] = sanitize_public_value(scrubbed.get("schedule"))
        scrubbed["notes"] = sanitize_public_text(scrubbed.get("notes"))
        if "last_operation" in scrubbed:
            scrubbed["last_operation"] = sanitize_public_value(
                scrubbed.get("last_operation")
            )
        return scrubbed

    def _normalize_registry(self, data: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(data, dict):
            return default_registry()
        data = deepcopy(data)
        data.setdefault("version", STORAGE_VERSION)
        data.setdefault("locks", {})
        if not isinstance(data["locks"], dict):
            data["locks"] = {}
        normalized_locks: dict[str, Any] = {}
        for entity_id, lock in data["locks"].items():
            if not isinstance(lock, dict):
                continue
            slots: dict[str, Any] = {}
            for slot_key, metadata in lock.get("slots", {}).items():
                try:
                    slot = int(slot_key)
                except (TypeError, ValueError):
                    continue
                slots[str(slot)] = self._scrub_slot_metadata(slot, metadata)
            if slots:
                normalized_locks[str(entity_id)] = {"slots": slots}
        data["locks"] = normalized_locks
        return data

    def _normalize_private_codes(self, data: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(data, dict):
            return default_private_codes()
        data = deepcopy(data)
        data.setdefault("version", STORAGE_VERSION)
        data.setdefault("codes", {})
        if not isinstance(data["codes"], dict):
            data["codes"] = {}
        return data

    def _lock_entry(self, entity_id: str) -> dict[str, Any]:
        lock = self._registry["locks"].setdefault(entity_id, {"slots": {}})
        lock.setdefault("slots", {})
        return lock

    def _slot_entry(self, entity_id: str, slot: int) -> dict[str, Any] | None:
        lock = self._registry["locks"].get(entity_id, {})
        return lock.get("slots", {}).get(str(slot))

    async def async_set_code_metadata(
        self,
        *,
        entity_id: str,
        slot: int,
        name: str,
        code: str,
        labels: Any = None,
        enabled: bool = True,
        starts_at: Any = None,
        expires_at: Any = None,
        schedule: Any = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Store safe metadata publicly and PIN material privately."""
        entity_id = validate_entity_id(entity_id)
        slot = validate_slot(slot, minimum=self.min_slot, maximum=self.max_slot)
        name = validate_name(name)
        code = validate_code(
            code,
            min_length=self.min_code_length,
            max_length=self.max_code_length,
        )
        slot_key = str(slot)
        lock = self._lock_entry(entity_id)
        metadata = {
            "name": sanitize_public_text(name, secrets=[code]) or f"Slot {slot}",
            "labels": sanitize_public_labels(labels, secrets=[code]),
            "enabled": bool(enabled),
            "starts_at": parse_datetime(starts_at),
            "expires_at": parse_datetime(expires_at),
            "schedule": sanitize_public_value(schedule, secrets=[code]),
            "code_length": len(code),
            "has_private_code": True,
            "notes": sanitize_public_text(notes, secrets=[code]),
            "updated_at": utcnow_iso(),
        }
        existing = lock["slots"].get(slot_key, {})
        if "last_operation" in existing:
            metadata["last_operation"] = deepcopy(existing["last_operation"])
        lock["slots"][slot_key] = metadata
        self._private_codes["codes"].setdefault(entity_id, {})[slot_key] = code
        await self.async_save()
        return deepcopy(metadata)

    async def async_remove_code_slot(self, *, entity_id: str, slot: int) -> None:
        """Remove registry metadata and private PIN after a successful lock clear."""
        entity_id = validate_entity_id(entity_id)
        slot = validate_slot(slot, minimum=self.min_slot, maximum=self.max_slot)
        slot_key = str(slot)
        lock = self._registry["locks"].get(entity_id)
        if lock:
            lock.get("slots", {}).pop(slot_key, None)
            if not lock.get("slots"):
                self._registry["locks"].pop(entity_id, None)
        codes_for_lock = self._private_codes["codes"].get(entity_id)
        if codes_for_lock:
            codes_for_lock.pop(slot_key, None)
            if not codes_for_lock:
                self._private_codes["codes"].pop(entity_id, None)
        await self.async_save()

    async def async_set_enabled(
        self,
        *,
        entity_id: str,
        slot: int,
        enabled: bool,
        update_desired: bool = True,
    ) -> None:
        """Update desired enabled state after a successful enable/disable service."""
        entity_id = validate_entity_id(entity_id)
        slot = validate_slot(slot, minimum=self.min_slot, maximum=self.max_slot)
        entry = self._slot_entry(entity_id, slot)
        if entry is not None and update_desired:
            entry["enabled"] = bool(enabled)
            entry["updated_at"] = utcnow_iso()
            await self.async_save()

    async def async_record_operation(
        self,
        *,
        entity_id: str,
        slot: int,
        operation: str,
        status: str,
        error: Any = None,
        secrets: list[str] | None = None,
    ) -> None:
        """Record sanitized operation status for troubleshooting."""
        entity_id = validate_entity_id(entity_id)
        slot = validate_slot(slot, minimum=self.min_slot, maximum=self.max_slot)
        entry = self._slot_entry(entity_id, slot)
        if entry is None:
            entry = {
                "name": f"Slot {slot}",
                "labels": [],
                "enabled": False,
                "starts_at": None,
                "expires_at": None,
                "schedule": None,
                "code_length": None,
                "has_private_code": False,
                "notes": None,
            }
            self._lock_entry(entity_id)["slots"][str(slot)] = entry
        entry["last_operation"] = {
            "operation": operation,
            "status": status,
            "error": redact_text(error, secrets=secrets) if error else None,
            "timestamp": utcnow_iso(),
        }
        await self.async_save()

    async def async_get_private_code(self, entity_id: str, slot: int) -> str | None:
        """Return a private code for an explicit internal apply/sync path."""
        entity_id = validate_entity_id(entity_id)
        slot = validate_slot(slot, minimum=self.min_slot, maximum=self.max_slot)
        return self._private_codes.get("codes", {}).get(entity_id, {}).get(str(slot))

    def iter_slots(
        self, entity_id: str | None = None
    ) -> list[tuple[str, int, dict[str, Any]]]:
        """Return public slot entries as deep copies."""
        results: list[tuple[str, int, dict[str, Any]]] = []
        locks = self._registry.get("locks", {})
        for lock_entity_id, lock in locks.items():
            if entity_id and lock_entity_id != entity_id:
                continue
            for slot_key, metadata in lock.get("slots", {}).items():
                try:
                    slot = int(slot_key)
                except (TypeError, ValueError):
                    continue
                results.append((lock_entity_id, slot, deepcopy(metadata)))
        return results

    def safe_summary(self, entity_id: str | None = None) -> dict[str, Any]:
        """Return registry summary safe for sensors/diagnostics."""
        locks: dict[str, Any] = {}
        for lock_entity_id, slot, metadata in self.iter_slots(entity_id):
            safe_meta = redact_data(metadata)
            locks.setdefault(lock_entity_id, {"slots": {}})["slots"][
                str(slot)
            ] = safe_meta
        return {
            "managed_lock_count": len(locks),
            "occupied_slot_count": sum(
                len(lock["slots"]) for lock in locks.values()
            ),
            "locks": locks,
        }
