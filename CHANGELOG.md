# Changelog

## v0.2.0 - 2026-06-17

### Added

- Home Assistant sidebar panel: **Lock Codes**.
- Lock entity dropdown populated from live `lock.*` Home Assistant entities.
- Sticky form state so Home Assistant frontend state updates do not reset partially entered code data.
- Per-slot masked current-PIN field with explicit administrator-only reveal action.
- Double-confirmed **Clear all configured slots** panel action.
- Safer **Clear known managed** panel action for clearing only slots recorded in the local registry.
- `zigbee_lock_manager.clear_all_codes` service with full configured-range clearing and `known_only` mode.
- Panel slot coverage display showing the configured managed range and total configured slots.
- Websocket summary endpoint for PIN-free panel data.
- Websocket private-code endpoint used only by explicit PIN reveal clicks.
- Tests for frontend summaries, private PIN reveal, clear-all behavior, services, scheduling, storage, diagnostics redaction, and config/options flows.

### Changed

- `manifest.json` version bumped to `0.2.0`.
- Service descriptions/docs clarify that `entity_id` belongs under service `data`, not a Home Assistant `target` block.
- README now documents the panel, clear-all behavior, PIN reveal model, slot coverage limits, and private storage trust boundary.

### Security / privacy

- Normal panel summaries remain PIN-free.
- Plaintext PINs are stored only in the dedicated Home Assistant private store (`Store(..., private=True, atomic_writes=True)`).
- PIN reveal is explicit, admin-gated, and not exposed through entity state, diagnostics, logs, or the default panel summary.

### Known limitations

- Public ZHA does not reliably expose existing lock-code readback/import.
- Public ZHA does not reliably expose the physical maximum supported user-code slot count; the panel shows the configured management range instead.
- Private Home Assistant storage persists across restarts but is not encryption-at-rest against host, backup, or admin access.
