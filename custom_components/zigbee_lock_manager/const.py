"""Constants and pure helpers for Zigbee Lock Manager."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

DOMAIN = "zigbee_lock_manager"
PLATFORMS: list[str] = ["sensor"]

CONF_LOCK_ENTITIES = "lock_entities"
CONF_MIN_SLOT = "min_slot"
CONF_MAX_SLOT = "max_slot"
CONF_MIN_CODE_LENGTH = "min_code_length"
CONF_MAX_CODE_LENGTH = "max_code_length"

DEFAULT_MIN_SLOT = 1
DEFAULT_MAX_SLOT = 30
DEFAULT_MIN_CODE_LENGTH = 4
DEFAULT_MAX_CODE_LENGTH = 8

MANAGER_DATA_KEY = "manager"
STORAGE_VERSION = 1
METADATA_STORE_KEY = f"{DOMAIN}.registry"
PRIVATE_CODE_STORE_KEY = f"{DOMAIN}.private_codes"

SERVICE_SET_CODE = "set_code"
SERVICE_CLEAR_CODE = "clear_code"
SERVICE_ENABLE_CODE = "enable_code"
SERVICE_DISABLE_CODE = "disable_code"
SERVICE_SYNC_REGISTRY = "sync_registry"
SERVICE_APPLY_REGISTRY = "apply_registry"
SERVICE_APPLY_SCHEDULES = "apply_schedules"
SERVICE_PROBE_SLOTS = "probe_slots"

ZHA_DOMAIN = "zha"
ZHA_SET_CODE_SERVICE = "set_lock_user_code"
ZHA_CLEAR_CODE_SERVICE = "clear_lock_user_code"
ZHA_ENABLE_CODE_SERVICE = "enable_lock_user_code"
ZHA_DISABLE_CODE_SERVICE = "disable_lock_user_code"

PUBLIC_SERVICE_NAMES = {
    SERVICE_SET_CODE,
    SERVICE_CLEAR_CODE,
    SERVICE_ENABLE_CODE,
    SERVICE_DISABLE_CODE,
    SERVICE_SYNC_REGISTRY,
    SERVICE_APPLY_REGISTRY,
    SERVICE_APPLY_SCHEDULES,
    SERVICE_PROBE_SLOTS,
}

SECRET_FIELD_NAMES = {
    "code",
    "pin",
    "user_code",
    "private_code",
    "secret",
    "password",
    "token",
}
SAFE_CODE_METADATA_FIELD_NAMES = {"code_length", "has_private_code"}
SAFE_TIMESTAMP_FIELD_NAMES = {"updated_at", "timestamp", "starts_at", "expires_at"}
_DIGIT_SECRET_RE = re.compile(r"(?<!\d)\d{4,12}(?!\d)")


class ZigbeeLockManagerError(Exception):
    """Base integration error."""


class ValidationError(ZigbeeLockManagerError, ValueError):
    """Raised when user supplied lock-code data is invalid."""


@dataclass(frozen=True, slots=True)
class SlotRange:
    """Validated inclusive slot range."""

    minimum: int = DEFAULT_MIN_SLOT
    maximum: int = DEFAULT_MAX_SLOT

    def __post_init__(self) -> None:
        validate_slot_range(self.minimum, self.maximum)

    def contains(self, slot: int) -> bool:
        """Return whether slot is inside the range."""
        return self.minimum <= slot <= self.maximum


def validate_slot_range(minimum: int, maximum: int) -> None:
    """Validate an inclusive positive slot range."""
    if not isinstance(minimum, int) or not isinstance(maximum, int):
        raise ValidationError("Slot range values must be integers")
    if minimum < 1:
        raise ValidationError("Minimum slot must be at least 1")
    if maximum < minimum:
        raise ValidationError("Maximum slot must be greater than or equal to minimum")


def validate_slot(
    slot: Any,
    *,
    minimum: int = DEFAULT_MIN_SLOT,
    maximum: int = DEFAULT_MAX_SLOT,
) -> int:
    """Return a validated positive slot integer in the configured range."""
    if isinstance(slot, bool):
        raise ValidationError("Slot must be an integer")
    try:
        slot_int = int(slot)
    except (TypeError, ValueError) as err:
        raise ValidationError("Slot must be an integer") from err
    validate_slot_range(minimum, maximum)
    if not minimum <= slot_int <= maximum:
        raise ValidationError(f"Slot must be between {minimum} and {maximum}")
    return slot_int


def validate_code(
    code: Any,
    *,
    min_length: int = DEFAULT_MIN_CODE_LENGTH,
    max_length: int = DEFAULT_MAX_CODE_LENGTH,
) -> str:
    """Return a validated Kwikset-safe numeric PIN string."""
    if not isinstance(code, str):
        raise ValidationError("Code must be a string")
    if not code.isdigit():
        raise ValidationError("Code must contain digits only")
    if not min_length <= len(code) <= max_length:
        raise ValidationError(
            f"Code must be between {min_length} and {max_length} digits"
        )
    return code


def validate_name(name: Any) -> str:
    """Return a validated non-empty display name."""
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Name is required")
    return name.strip()


def validate_entity_id(entity_id: Any) -> str:
    """Return a validated Home Assistant entity_id-ish string."""
    if not isinstance(entity_id, str) or "." not in entity_id or not entity_id.strip():
        raise ValidationError("entity_id must be a Home Assistant entity id")
    return entity_id.strip()


def normalize_labels(labels: Any) -> list[str]:
    """Normalize labels from a string, iterable, or missing value."""
    if labels is None or labels == "":
        return []
    if isinstance(labels, str):
        raw = [item.strip() for item in labels.split(",")]
    elif isinstance(labels, Iterable):
        raw = [str(item).strip() for item in labels]
    else:
        raise ValidationError("labels must be a comma-separated string or list")
    return sorted({item for item in raw if item})


def parse_datetime(value: Any) -> str | None:
    """Normalize optional date/datetime values to ISO strings.

    HA service data commonly supplies datetime objects, ISO strings, or None.
    The registry stores ISO strings to keep metadata JSON-safe and PIN-free.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as err:
            raise ValidationError("datetime values must be ISO 8601 strings") from err
        return value
    raise ValidationError("datetime values must be ISO 8601 strings or datetimes")


def mask_code(code: str | None) -> str | None:
    """Return a display mask preserving only length."""
    if code is None:
        return None
    return "•" * len(code)


def redact_text(value: Any, *, secrets: Iterable[str] | None = None) -> str:
    """Redact likely PIN material from a string for logs/status/errors."""
    text = str(value)
    for secret in secrets or []:
        if secret:
            text = text.replace(str(secret), "[REDACTED]")
    return _DIGIT_SECRET_RE.sub("[REDACTED]", text)


def redact_data(data: Any, *, secrets: Iterable[str] | None = None) -> Any:
    """Recursively redact dictionaries/lists before diagnostics or status exposure."""
    if isinstance(data, Mapping):
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if key_lower in SAFE_CODE_METADATA_FIELD_NAMES | SAFE_TIMESTAMP_FIELD_NAMES:
                redacted[key_str] = value
            elif key_lower in SECRET_FIELD_NAMES or any(
                marker in key_lower for marker in ("code", "pin", "secret")
            ):
                redacted[key_str] = "[REDACTED]"
            else:
                redacted[key_str] = redact_data(value, secrets=secrets)
        return redacted
    if isinstance(data, list):
        return [redact_data(item, secrets=secrets) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_data(item, secrets=secrets) for item in data)
    if isinstance(data, str):
        return redact_text(data, secrets=secrets)
    return data
