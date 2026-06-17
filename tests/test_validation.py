from __future__ import annotations

import pytest
from custom_components.zigbee_lock_manager.const import (
    ValidationError,
    mask_code,
    normalize_labels,
    redact_data,
    redact_text,
    validate_code,
    validate_name,
    validate_slot,
)


def test_validate_kwikset_default_code_rules() -> None:
    assert validate_code("1234") == "1234"
    assert validate_code("12345678") == "12345678"
    for bad in ["123", "123456789", "12a4", 1234, "12 34"]:
        with pytest.raises(ValidationError):
            validate_code(bad)


def test_validate_slot_default_range() -> None:
    assert validate_slot("1") == 1
    assert validate_slot(30) == 30
    for bad in [0, 31, "x", True]:
        with pytest.raises(ValidationError):
            validate_slot(bad)


def test_validate_name_and_labels() -> None:
    assert validate_name(" Micheal ") == "Micheal"
    with pytest.raises(ValidationError):
        validate_name(" ")
    assert normalize_labels(" household, guest, household ") == ["guest", "household"]
    assert normalize_labels(["guest", "dog walker"]) == ["dog walker", "guest"]


def test_mask_and_redaction_without_public_fingerprint() -> None:
    assert mask_code("123456") == "••••••"
    assert "123456" not in redact_text("bad PIN 123456 failed")
    redacted = redact_data({"user_code": "123456", "nested": {"message": "pin 123456"}})
    assert redacted["user_code"] == "[REDACTED]"
    assert "123456" not in str(redacted)
