"""Shared lightweight test fakes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from custom_components.zigbee_lock_manager.manager import ZigbeeLockManager
from custom_components.zigbee_lock_manager.storage import (
    LockRegistryStore,
    MemoryStoreBackend,
)


class FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], bool]] = []
        self.registered: dict[tuple[str, str], Any] = {}
        self.register_calls = 0
        self.raise_on_call: Exception | None = None

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        blocking: bool = False,
    ) -> None:
        self.calls.append((domain, service, dict(data), blocking))
        if self.raise_on_call is not None:
            raise self.raise_on_call

    def async_register(
        self,
        domain: str,
        service: str,
        handler: Any,
        schema: Any = None,
    ) -> None:
        self.register_calls += 1
        self.registered[(domain, service)] = (handler, schema)


class FakeConfigEntries:
    def __init__(self) -> None:
        self.reloaded_entry_ids: list[str] = []

    async def async_forward_entry_setups(
        self, _entry: Any, _platforms: list[str]
    ) -> None:
        return None

    async def async_unload_platforms(self, _entry: Any, _platforms: list[str]) -> bool:
        return True

    async def async_reload(self, entry_id: str) -> None:
        self.reloaded_entry_ids.append(entry_id)


class FakeHass:
    def __init__(self) -> None:
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()
        self.data: dict[str, Any] = {}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def make_registry() -> LockRegistryStore:
    registry = LockRegistryStore(MemoryStoreBackend(), MemoryStoreBackend())
    await registry.async_load()
    return registry


async def make_manager() -> tuple[FakeHass, ZigbeeLockManager]:
    hass = FakeHass()
    registry = await make_registry()
    return hass, ZigbeeLockManager(hass, registry)


def fake_entry(**kwargs: Any) -> Any:
    defaults = {
        "entry_id": "entry-1",
        "title": "Zigbee Lock Manager",
        "data": {},
        "options": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)
