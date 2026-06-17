"""Config flow for Zigbee Lock Manager."""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_LOCK_ENTITIES,
    CONF_MAX_CODE_LENGTH,
    CONF_MAX_SLOT,
    CONF_MIN_CODE_LENGTH,
    CONF_MIN_SLOT,
    DEFAULT_MAX_CODE_LENGTH,
    DEFAULT_MAX_SLOT,
    DEFAULT_MIN_CODE_LENGTH,
    DEFAULT_MIN_SLOT,
    DOMAIN,
    validate_slot_range,
)

try:  # pragma: no cover - exercised in Home Assistant, faked in unit tests
    import voluptuous as vol  # type: ignore[import-not-found]
    from homeassistant import config_entries  # type: ignore[import-not-found]
    from homeassistant.helpers import selector  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - lightweight local-test fallback
    vol = None

    class _FallbackFlow:
        def __init_subclass__(cls, **_kwargs: Any) -> None:
            super().__init_subclass__()

        async def async_set_unique_id(self, _unique_id: str) -> None:
            self._unique_id = _unique_id

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "create_entry", **kwargs}

    class _FallbackConfigEntries:
        ConfigFlow = _FallbackFlow
        OptionsFlow = _FallbackFlow
        ConfigEntry = object

    class _FallbackSelector:
        @staticmethod
        def EntitySelector(_config: Any = None) -> object:
            return object()

        @staticmethod
        def EntitySelectorConfig(**kwargs: Any) -> dict[str, Any]:
            return kwargs

        @staticmethod
        def NumberSelector(_config: Any = None) -> object:
            return object()

        @staticmethod
        def NumberSelectorConfig(**kwargs: Any) -> dict[str, Any]:
            return kwargs

    config_entries = _FallbackConfigEntries()
    selector = _FallbackSelector()


def _schema(defaults: dict[str, Any] | None = None) -> Any:
    """Return the setup/options schema, or a dict fallback without HA deps."""
    defaults = defaults or {}
    if vol is None:
        return {
            CONF_LOCK_ENTITIES: defaults.get(CONF_LOCK_ENTITIES, []),
            CONF_MIN_SLOT: defaults.get(CONF_MIN_SLOT, DEFAULT_MIN_SLOT),
            CONF_MAX_SLOT: defaults.get(CONF_MAX_SLOT, DEFAULT_MAX_SLOT),
            CONF_MIN_CODE_LENGTH: defaults.get(
                CONF_MIN_CODE_LENGTH, DEFAULT_MIN_CODE_LENGTH
            ),
            CONF_MAX_CODE_LENGTH: defaults.get(
                CONF_MAX_CODE_LENGTH, DEFAULT_MAX_CODE_LENGTH
            ),
        }
    return vol.Schema(
        {
            vol.Optional(
                CONF_LOCK_ENTITIES,
                default=defaults.get(CONF_LOCK_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="lock", multiple=True)
            ),
            vol.Optional(
                CONF_MIN_SLOT,
                default=defaults.get(CONF_MIN_SLOT, DEFAULT_MIN_SLOT),
            ): int,
            vol.Optional(
                CONF_MAX_SLOT,
                default=defaults.get(CONF_MAX_SLOT, DEFAULT_MAX_SLOT),
            ): int,
            vol.Optional(
                CONF_MIN_CODE_LENGTH,
                default=defaults.get(CONF_MIN_CODE_LENGTH, DEFAULT_MIN_CODE_LENGTH),
            ): int,
            vol.Optional(
                CONF_MAX_CODE_LENGTH,
                default=defaults.get(CONF_MAX_CODE_LENGTH, DEFAULT_MAX_CODE_LENGTH),
            ): int,
        }
    )


def _validate_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize config flow user input."""
    min_slot = int(user_input.get(CONF_MIN_SLOT, DEFAULT_MIN_SLOT))
    max_slot = int(user_input.get(CONF_MAX_SLOT, DEFAULT_MAX_SLOT))
    validate_slot_range(min_slot, max_slot)
    min_len = int(user_input.get(CONF_MIN_CODE_LENGTH, DEFAULT_MIN_CODE_LENGTH))
    max_len = int(user_input.get(CONF_MAX_CODE_LENGTH, DEFAULT_MAX_CODE_LENGTH))
    if min_len < 1 or max_len < min_len:
        raise ValueError("invalid_code_length")
    locks = user_input.get(CONF_LOCK_ENTITIES, []) or []
    if isinstance(locks, str):
        locks = [locks]
    return {
        CONF_LOCK_ENTITIES: list(locks),
        CONF_MIN_SLOT: min_slot,
        CONF_MAX_SLOT: max_slot,
        CONF_MIN_CODE_LENGTH: min_len,
        CONF_MAX_CODE_LENGTH: max_len,
    }


class ZigbeeLockManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create the integration with optional initial lock entities."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _validate_user_input(user_input)
            except Exception:
                errors["base"] = "invalid_input"
            else:
                return self.async_create_entry(title="Zigbee Lock Manager", data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: Any) -> ZigbeeLockManagerOptionsFlow:
        """Return options flow handler."""
        return ZigbeeLockManagerOptionsFlow(config_entry)


class ZigbeeLockManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle options updates."""

    def __init__(self, config_entry: Any) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        defaults = {**getattr(self.config_entry, "data", {})}
        defaults.update(getattr(self.config_entry, "options", {}) or {})
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _validate_user_input(user_input)
            except Exception:
                errors["base"] = "invalid_input"
            else:
                return self.async_create_entry(title="", data=data)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults),
            errors=errors,
        )
