from __future__ import annotations

from pathlib import Path

SERVICES_YAML = (
    Path(__file__).parents[1]
    / "custom_components"
    / "zigbee_lock_manager"
    / "services.yaml"
)


def test_services_use_data_entity_id_not_ha_target_block() -> None:
    content = SERVICES_YAML.read_text()
    assert "target:" not in content
    assert "entity_id:" in content
