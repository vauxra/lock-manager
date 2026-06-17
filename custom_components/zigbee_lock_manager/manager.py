"""ZHA service adapter and service-first lock code manager."""

from __future__ import annotations

from typing import Any

from .const import (
    DEFAULT_MAX_CODE_LENGTH,
    DEFAULT_MAX_SLOT,
    DEFAULT_MIN_CODE_LENGTH,
    DEFAULT_MIN_SLOT,
    SERVICE_APPLY_REGISTRY,
    SERVICE_APPLY_SCHEDULES,
    SERVICE_CLEAR_CODE,
    SERVICE_DISABLE_CODE,
    SERVICE_ENABLE_CODE,
    SERVICE_PROBE_SLOTS,
    SERVICE_SET_CODE,
    SERVICE_SYNC_REGISTRY,
    ZHA_CLEAR_CODE_SERVICE,
    ZHA_DISABLE_CODE_SERVICE,
    ZHA_DOMAIN,
    ZHA_ENABLE_CODE_SERVICE,
    ZHA_SET_CODE_SERVICE,
    ValidationError,
    redact_text,
    validate_code,
    validate_entity_id,
    validate_name,
    validate_slot,
)
from .scheduler import LockScheduleCoordinator, desired_operation_for_slot
from .storage import LockRegistryStore


class ZigbeeLockManager:
    """Coordinates validation, ZHA service calls, registry updates, and schedules."""

    def __init__(
        self,
        hass: Any,
        registry: LockRegistryStore,
        *,
        min_slot: int = DEFAULT_MIN_SLOT,
        max_slot: int = DEFAULT_MAX_SLOT,
        min_code_length: int = DEFAULT_MIN_CODE_LENGTH,
        max_code_length: int = DEFAULT_MAX_CODE_LENGTH,
    ) -> None:
        self.hass = hass
        self.registry = registry
        self.min_slot = min_slot
        self.max_slot = max_slot
        self.min_code_length = min_code_length
        self.max_code_length = max_code_length
        self.scheduler = LockScheduleCoordinator(self)

    async def _call_zha(self, service: str, payload: dict[str, Any]) -> None:
        await self.hass.services.async_call(
            ZHA_DOMAIN,
            service,
            payload,
            blocking=True,
        )

    def _validate_slot(self, slot: Any) -> int:
        return validate_slot(slot, minimum=self.min_slot, maximum=self.max_slot)

    def _validate_code(self, code: Any) -> str:
        return validate_code(
            code,
            min_length=self.min_code_length,
            max_length=self.max_code_length,
        )

    async def set_code(
        self,
        entity_id: str,
        slot: int,
        code: str,
        *,
        name: str,
        labels: Any = None,
        enabled: bool = True,
        starts_at: Any = None,
        expires_at: Any = None,
        schedule: Any = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Store a code and program it only when currently active.

        Disabled, future, or expired codes are stored in the private registry but
        are not sent as usable PINs to the lock. This avoids briefly activating
        scheduled/disabled access if a follow-up disable command fails.
        """
        entity_id = validate_entity_id(entity_id)
        slot = self._validate_slot(slot)
        code = self._validate_code(code)
        name = validate_name(name)

        metadata = await self.registry.async_set_code_metadata(
            entity_id=entity_id,
            slot=slot,
            name=name,
            code=code,
            labels=labels,
            enabled=enabled,
            starts_at=starts_at,
            expires_at=expires_at,
            schedule=schedule,
            notes=notes,
        )
        operation, reason = desired_operation_for_slot(metadata)
        if operation == "disable":
            # Disabled/future/expired codes are physically disabled and never
            # sent as usable PINs. If the disable call fails it propagates; the
            # private PIN is preserved for a later apply/reconcile.
            await self.disable_code(
                entity_id,
                slot,
                scheduled=True,
                update_desired=False,
            )
            await self.registry.async_record_operation(
                entity_id=entity_id,
                slot=slot,
                operation=SERVICE_SET_CODE,
                status=f"stored_{reason}",
            )
            return metadata

        payload = {"entity_id": entity_id, "code_slot": slot, "user_code": code}
        try:
            await self._call_zha(ZHA_SET_CODE_SERVICE, payload)
        except Exception as err:
            await self.registry.async_record_operation(
                entity_id=entity_id,
                slot=slot,
                operation=SERVICE_SET_CODE,
                status="failed",
                error=err,
                secrets=[code],
            )
            raise

        await self.registry.async_record_operation(
            entity_id=entity_id,
            slot=slot,
            operation=SERVICE_SET_CODE,
            status="success",
        )
        return metadata

    async def clear_code(self, entity_id: str, slot: int) -> None:
        """Clear a user-code slot through ZHA, then remove local registry data."""
        entity_id = validate_entity_id(entity_id)
        slot = self._validate_slot(slot)
        try:
            await self._call_zha(
                ZHA_CLEAR_CODE_SERVICE,
                {"entity_id": entity_id, "code_slot": slot},
            )
        except Exception as err:
            await self.registry.async_record_operation(
                entity_id=entity_id,
                slot=slot,
                operation=SERVICE_CLEAR_CODE,
                status="failed",
                error=err,
            )
            raise
        await self.registry.async_remove_code_slot(entity_id=entity_id, slot=slot)

    async def enable_code(
        self,
        entity_id: str,
        slot: int,
        *,
        scheduled: bool = False,
        update_desired: bool = True,
    ) -> None:
        """Enable a slot through ZHA and update safe operation state."""
        entity_id = validate_entity_id(entity_id)
        slot = self._validate_slot(slot)
        operation = "scheduled_enable" if scheduled else SERVICE_ENABLE_CODE
        private_code = await self.registry.async_get_private_code(entity_id, slot)
        try:
            if private_code:
                await self._call_zha(
                    ZHA_SET_CODE_SERVICE,
                    {
                        "entity_id": entity_id,
                        "code_slot": slot,
                        "user_code": private_code,
                    },
                )
            await self._call_zha(
                ZHA_ENABLE_CODE_SERVICE,
                {"entity_id": entity_id, "code_slot": slot},
            )
        except Exception as err:
            await self.registry.async_record_operation(
                entity_id=entity_id,
                slot=slot,
                operation=operation,
                status="failed",
                error=err,
                secrets=[private_code] if private_code else None,
            )
            raise
        await self.registry.async_set_enabled(
            entity_id=entity_id,
            slot=slot,
            enabled=True,
            update_desired=update_desired,
        )
        await self.registry.async_record_operation(
            entity_id=entity_id,
            slot=slot,
            operation=operation,
            status="success",
        )

    async def disable_code(
        self,
        entity_id: str,
        slot: int,
        *,
        scheduled: bool = False,
        update_desired: bool = True,
    ) -> None:
        """Disable a slot through ZHA and update safe operation state."""
        entity_id = validate_entity_id(entity_id)
        slot = self._validate_slot(slot)
        operation = "scheduled_disable" if scheduled else SERVICE_DISABLE_CODE
        try:
            await self._call_zha(
                ZHA_DISABLE_CODE_SERVICE,
                {"entity_id": entity_id, "code_slot": slot},
            )
        except Exception as err:
            await self.registry.async_record_operation(
                entity_id=entity_id,
                slot=slot,
                operation=operation,
                status="failed",
                error=err,
            )
            raise
        await self.registry.async_set_enabled(
            entity_id=entity_id,
            slot=slot,
            enabled=False,
            update_desired=update_desired,
        )
        await self.registry.async_record_operation(
            entity_id=entity_id,
            slot=slot,
            operation=operation,
            status="success",
        )

    async def apply_registry(
        self, entity_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Re-apply locally stored registry intent to ZHA locks safely.

        Active slots are programmed from the private store. Disabled, future, or
        expired slots are disabled only and never reprogrammed as usable codes.
        """
        results: list[dict[str, Any]] = []
        for lock_entity_id, slot, metadata in self.registry.iter_slots(entity_id):
            private_code = await self.registry.async_get_private_code(
                lock_entity_id, slot
            )
            operation, reason = desired_operation_for_slot(metadata)
            if operation == "disable":
                try:
                    await self.disable_code(
                        lock_entity_id,
                        slot,
                        scheduled=True,
                        update_desired=False,
                    )
                except Exception:
                    status = "failed"
                else:
                    status = f"disabled_{reason}"
                results.append(
                    {
                        "entity_id": lock_entity_id,
                        "slot": slot,
                        "name": metadata.get("name"),
                        "status": status,
                    }
                )
                continue
            if not private_code:
                continue
            try:
                await self._call_zha(
                    ZHA_SET_CODE_SERVICE,
                    {
                        "entity_id": lock_entity_id,
                        "code_slot": slot,
                        "user_code": private_code,
                    },
                )
                await self._call_zha(
                    ZHA_ENABLE_CODE_SERVICE,
                    {"entity_id": lock_entity_id, "code_slot": slot},
                )
            except Exception as err:
                await self.registry.async_record_operation(
                    entity_id=lock_entity_id,
                    slot=slot,
                    operation=SERVICE_APPLY_REGISTRY,
                    status="failed",
                    error=err,
                    secrets=[private_code],
                )
                results.append(
                    {
                        "entity_id": lock_entity_id,
                        "slot": slot,
                        "name": metadata.get("name"),
                        "status": "failed",
                    }
                )
                continue
            await self.registry.async_record_operation(
                entity_id=lock_entity_id,
                slot=slot,
                operation=SERVICE_APPLY_REGISTRY,
                status="success",
            )
            results.append(
                {
                    "entity_id": lock_entity_id,
                    "slot": slot,
                    "name": metadata.get("name"),
                    "status": "success",
                }
            )
        return results

    async def apply_schedules(self, entity_id: str | None = None) -> list[Any]:
        """Apply current schedule state immediately."""
        if entity_id is not None:
            entity_id = validate_entity_id(entity_id)
        return await self.scheduler.async_reconcile(entity_id=entity_id)

    async def probe_slots(
        self,
        entity_id: str | None = None,
        *,
        start_slot: int | None = None,
        end_slot: int | None = None,
    ) -> dict[str, Any]:
        """Best-effort non-blocking slot probe stub.

        Public ZHA does not expose a supported get-user-code action. The MVP
        returns a safe capability result instead of guessing slot contents.
        """
        if entity_id is not None:
            entity_id = validate_entity_id(entity_id)
        if start_slot is not None:
            self._validate_slot(start_slot)
        if end_slot is not None:
            self._validate_slot(end_slot)
        return {
            "supported": False,
            "entity_id": entity_id,
            "slot_range": [
                start_slot or self.min_slot,
                end_slot or self.max_slot,
            ],
            "message": redact_text(
                "Slot probing is not available through public ZHA services."
            ),
        }

    async def handle_service_call(self, service: str, data: dict[str, Any]) -> Any:
        """Dispatch a Home Assistant service call to manager methods."""
        if service == SERVICE_SET_CODE:
            return await self.set_code(
                data["entity_id"],
                data["slot"],
                data["code"],
                name=data["name"],
                labels=data.get("labels"),
                enabled=data.get("enabled", True),
                starts_at=data.get("starts_at"),
                expires_at=data.get("expires_at"),
                schedule=data.get("schedule"),
                notes=data.get("notes"),
            )
        if service == SERVICE_CLEAR_CODE:
            return await self.clear_code(data["entity_id"], data["slot"])
        if service == SERVICE_ENABLE_CODE:
            return await self.enable_code(data["entity_id"], data["slot"])
        if service == SERVICE_DISABLE_CODE:
            return await self.disable_code(data["entity_id"], data["slot"])
        if service in {SERVICE_APPLY_REGISTRY, SERVICE_SYNC_REGISTRY}:
            return await self.apply_registry(data.get("entity_id"))
        if service == SERVICE_APPLY_SCHEDULES:
            return await self.apply_schedules(data.get("entity_id"))
        if service == SERVICE_PROBE_SLOTS:
            return await self.probe_slots(
                data.get("entity_id"),
                start_slot=data.get("start_slot"),
                end_slot=data.get("end_slot"),
            )
        raise ValidationError(f"Unknown service: {service}")
