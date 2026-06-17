"""Schedule reconciliation helpers for Zigbee Lock Manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

ScheduleOperation = Literal["enable", "disable"]


@dataclass(frozen=True, slots=True)
class ScheduleAction:
    """A physical enable/disable action needed to reconcile schedule state."""

    entity_id: str
    slot: int
    operation: ScheduleOperation
    reason: str


def parse_time(value: Any) -> datetime | None:
    """Parse optional ISO datetime metadata."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("schedule datetime must be a datetime or ISO string")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def normalize_now(now: datetime | None = None) -> datetime:
    """Return a timezone-aware UTC-ish now for comparisons."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def desired_operation_for_slot(
    metadata: dict[str, Any], now: datetime | None = None
) -> tuple[ScheduleOperation | None, str | None]:
    """Return the operation required by starts_at/expires_at metadata.

    Expiration wins and disables only. Starts in the future also disables the
    physical slot while keeping the user's desired enabled state in metadata.
    When inside the active window, the slot is enabled only if the registry's
    desired state is enabled.
    """
    now = normalize_now(now)
    starts_at = parse_time(metadata.get("starts_at"))
    expires_at = parse_time(metadata.get("expires_at"))
    desired_enabled = bool(metadata.get("enabled", True))

    if expires_at is not None and now >= expires_at:
        return "disable", "expired"
    if starts_at is not None and now < starts_at:
        return "disable", "not_started"
    if desired_enabled:
        return "enable", "active"
    return "disable", "desired_disabled"


def build_schedule_actions(
    registry: dict[str, Any],
    now: datetime | None = None,
    *,
    entity_id: str | None = None,
) -> list[ScheduleAction]:
    """Build restart/reload reconciliation actions for every registered slot."""
    actions: list[ScheduleAction] = []
    for lock_entity_id, lock in registry.get("locks", {}).items():
        if entity_id and lock_entity_id != entity_id:
            continue
        for slot_key, metadata in lock.get("slots", {}).items():
            operation, reason = desired_operation_for_slot(metadata, now)
            if operation and reason:
                actions.append(
                    ScheduleAction(
                        entity_id=lock_entity_id,
                        slot=int(slot_key),
                        operation=operation,
                        reason=reason,
                    )
                )
    return actions


class LockScheduleCoordinator:
    """Small HA-facing scheduler facade.

    MVP reconciliation is explicit and testable: on setup/reload or service call,
    build due actions and execute them through the manager. This avoids ad-hoc
    sleep loops while still representing restart reconciliation behavior.
    """

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self._unsubscribers: list[Callable[[], None]] = []

    def async_cancel_timers(self) -> None:
        """Cancel scheduled HA time callbacks."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    async def async_schedule_timers(self) -> None:
        """Schedule future starts/expires with Home Assistant time helpers.

        The pure reconciliation path remains testable without HA. When running
        inside HA, this uses `async_track_point_in_time` rather than sleep loops.
        """
        self.async_cancel_timers()
        try:
            from homeassistant.helpers.event import (
                async_track_point_in_time,  # type: ignore[import-not-found]
            )
        except Exception:  # pragma: no cover - local lightweight tests
            return

        now = normalize_now()
        seen: set[datetime] = set()
        for _entity_id, _slot, metadata in self.manager.registry.iter_slots():
            for key in ("starts_at", "expires_at"):
                when = parse_time(metadata.get(key))
                if when is None or when <= now or when in seen:
                    continue
                seen.add(when)

                async def _reconcile_at_time(_now: datetime) -> None:
                    await self.async_reconcile(now=_now)
                    await self.async_schedule_timers()

                self._unsubscribers.append(
                    async_track_point_in_time(
                        self.manager.hass, _reconcile_at_time, when
                    )
                )

    async def async_reconcile(
        self,
        *,
        now: datetime | None = None,
        entity_id: str | None = None,
    ) -> list[ScheduleAction]:
        """Apply all schedule actions that should hold at the supplied time."""
        actions = build_schedule_actions(
            self.manager.registry.public_registry,
            now,
            entity_id=entity_id,
        )
        for action in actions:
            if action.operation == "enable":
                await self.manager.enable_code(
                    action.entity_id,
                    action.slot,
                    scheduled=True,
                    update_desired=False,
                )
            else:
                await self.manager.disable_code(
                    action.entity_id,
                    action.slot,
                    scheduled=True,
                    update_desired=False,
                )
        return actions
