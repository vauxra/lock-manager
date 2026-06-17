from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.zigbee_lock_manager.scheduler import (
    build_schedule_actions,
    desired_operation_for_slot,
)

from .conftest import make_manager, run


def test_schedule_not_started_active_and_expired() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert desired_operation_for_slot(
        {"enabled": True, "starts_at": (now + timedelta(hours=1)).isoformat()}, now
    ) == ("disable", "not_started")
    assert desired_operation_for_slot(
        {"enabled": True, "starts_at": (now - timedelta(hours=1)).isoformat()}, now
    ) == ("enable", "active")
    assert desired_operation_for_slot(
        {"enabled": True, "expires_at": (now - timedelta(seconds=1)).isoformat()}, now
    ) == ("disable", "expired")
    assert desired_operation_for_slot({"enabled": False}, now) == (
        "disable",
        "desired_disabled",
    )


def test_build_schedule_actions_for_restart_reconciliation() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    registry = {
        "locks": {
            "lock.front_door": {
                "slots": {
                    "1": {
                        "enabled": True,
                        "expires_at": (now - timedelta(days=1)).isoformat(),
                    },
                    "2": {
                        "enabled": True,
                        "starts_at": (now - timedelta(days=1)).isoformat(),
                    },
                }
            }
        }
    }
    actions = build_schedule_actions(registry, now)
    assert [(a.entity_id, a.slot, a.operation, a.reason) for a in actions] == [
        ("lock.front_door", 1, "disable", "expired"),
        ("lock.front_door", 2, "enable", "active"),
    ]


def test_scheduler_reconcile_calls_manager_without_changing_desired_state() -> None:
    async def scenario() -> None:
        hass, manager = await make_manager()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        await manager.registry.async_set_code_metadata(
            entity_id="lock.front_door",
            slot=1,
            name="Guest",
            code="123456",
            enabled=True,
            expires_at=(now - timedelta(minutes=1)).isoformat(),
        )
        actions = await manager.scheduler.async_reconcile(now=now)
        assert len(actions) == 1
        assert hass.services.calls[-1][:3] == (
            "zha",
            "disable_lock_user_code",
            {"entity_id": "lock.front_door", "code_slot": 1},
        )
        public_slot = manager.registry.public_registry["locks"]["lock.front_door"][
            "slots"
        ]["1"]
        assert public_slot["enabled"] is True
        assert public_slot["last_operation"]["operation"] == "scheduled_disable"
        assert "123456" not in str(public_slot["last_operation"])

    run(scenario())
