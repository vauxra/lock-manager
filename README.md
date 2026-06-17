[![AI-DECLARATION: copilot](https://img.shields.io/badge/䷼%20AI--DECLARATION-copilot-fee2e2?labelColor=fee2e2)](https://ai-declaration.md)

# Zigbee Lock Manager

A HACS-style Home Assistant custom integration for managing Zigbee lock user-code slots through ZHA. It provides a Home Assistant sidebar panel, services, a private PIN store, safe metadata registry, schedule reconciliation, and a redacted summary sensor.

## Scope

- Domain: `zigbee_lock_manager`
- Baseline: Home Assistant `2026.2.2`
- Primary target: Kwikset Zigbee locks paired through ZHA
- ZHA actions used:
  - `zha.set_lock_user_code`
  - `zha.clear_lock_user_code`
  - `zha.enable_lock_user_code`
  - `zha.disable_lock_user_code`

## Security model for PINs

PINs are recallable/editable by the integration, but plaintext PINs are stored only in a dedicated Home Assistant private storage file created with `Store(..., private=True, atomic_writes=True)`. Safe metadata is stored separately in a public registry.

The integration does **not** store PINs in config entries/options, helpers, entity state/attributes, diagnostics, logs, events, traces, or repairs. Sensors and diagnostics expose counts and redacted metadata only. `private=True` is a file-permission/privacy feature, not encryption at rest; HA host access, backups, and administrators should be treated as trusted.

## Installation

### HACS custom repository

1. In HACS, add this repository as a custom integration repository.
2. Install **Zigbee Lock Manager**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and add **Zigbee Lock Manager**.
5. Optionally select managed lock entities and adjust the managed slot/PIN limits.
6. Open the **Lock Codes** sidebar panel to manage codes from the UI.

### Manual install

Copy `custom_components/zigbee_lock_manager` into your Home Assistant `config/custom_components/` directory, restart Home Assistant, then add the integration from the UI.

## Sidebar panel

After adding the integration, Home Assistant shows a **Lock Codes** panel in the sidebar for administrators. This is the normal way to configure and manage lock codes; you should not need the Developer Tools actions menu for day-to-day use.

Use the panel to:

- choose a lock entity from the dropdown;
- set/update a PIN for a slot;
- label a slot;
- set optional start/expiration times;
- enable, disable, or clear managed slots;
- clear only known managed slots after confirmation;
- clear every slot in the configured slot range after explicit confirmation;
- reveal a stored PIN only by clicking the per-slot eye button;
- refresh the redacted registry view.

The panel accepts PINs in the write form and stores them in the private store. Normal summary data stays PIN-free; the current PIN field is masked and only fetches a private PIN after an explicit administrator reveal click.

The panel shows the configured slot range, for example `1–30 (30 total)`. Public ZHA does not reliably expose the physical lock's maximum supported user-code slot count, so the configured range is the operational coverage the integration can guarantee.

## Configuring managed locks and slot limits

Open **Settings → Devices & services → Zigbee Lock Manager → Configure** to update integration options:

- managed lock entities shown in the panel;
- minimum and maximum managed slot numbers;
- minimum and maximum accepted PIN length.

The panel dropdown also includes live Home Assistant `lock.*` entities, so newly discovered locks can be selected without typing entity IDs.

## Services for automations and advanced use

The sidebar panel is the recommended interface. The same operations are also available as services for automations, scripts, or troubleshooting. If you use services directly, put `entity_id` under `data`, not under a Home Assistant `target` block.

### Set a code

```yaml
service: zigbee_lock_manager.set_code
data:
  entity_id: lock.front_door
  slot: 1
  name: Micheal
  labels:
    - household
  code: "123456"
  enabled: true
  starts_at: null
  expires_at: "2026-12-31T23:59:00-05:00"
  notes: "Example managed slot"
```

The integration validates the PIN as 4–8 digits by default, calls `zha.set_lock_user_code`, then stores only safe metadata publicly and the PIN in the private code store.

### Clear a code

```yaml
service: zigbee_lock_manager.clear_code
data:
  entity_id: lock.front_door
  slot: 1
```

A successful clear removes both the safe registry metadata and private PIN copy for that slot.

### Clear all configured slots

```yaml
service: zigbee_lock_manager.clear_all_codes
data:
  entity_id: lock.front_door
  start_slot: 1
  end_slot: 30
  known_only: false
```

Clears every slot in the supplied/configured range by calling `zha.clear_lock_user_code` per slot. Use this carefully: it can remove working codes from the physical lock. Set `known_only: true` to clear only slots already present in the local manager registry. The panel exposes both paths: **Clear known managed** for local-registry slots and **Clear all** for the configured range.

### Enable or disable a code

```yaml
service: zigbee_lock_manager.enable_code
data:
  entity_id: lock.front_door
  slot: 1
```

```yaml
service: zigbee_lock_manager.disable_code
data:
  entity_id: lock.front_door
  slot: 1
```

### Apply registry

```yaml
service: zigbee_lock_manager.apply_registry
data:
  entity_id: lock.front_door
```

Re-applies locally stored registry intent to ZHA. This path retrieves private PINs internally only to send `zha.set_lock_user_code`; it does not return or expose PINs.

`zigbee_lock_manager.sync_registry` is provided as an alias for the same MVP behavior.

### Apply schedules

```yaml
service: zigbee_lock_manager.apply_schedules
data:
  entity_id: lock.front_door
```

Reconciles `starts_at`, `expires_at`, and desired `enabled` metadata immediately. Expired slots are disabled only; PINs are never cleared/deleted automatically by expiration.

### Probe slots

```yaml
service: zigbee_lock_manager.probe_slots
data:
  entity_id: lock.front_door
  start_slot: 1
  end_slot: 30
```

Public ZHA does not expose a supported read/get user-code service, so the MVP probe is a safe best-effort capability stub. It never assumes unknown slots are empty and never blocks normal service-based management.

## Registry metadata

Public metadata includes values such as lock `entity_id`, slot, redacted name/labels, desired enabled state, schedule dates, PIN length, private-code presence, redacted notes, and last operation status/error timestamp. Plaintext PINs and brute-forceable PIN fingerprints are never intentionally present in this public registry.

## Known limitations

- ZHA only for MVP; Zigbee2MQTT and Z-Wave JS are future adapter candidates.
- No guaranteed import/readback of existing lock codes.
- No automatic physical max-slot discovery through public ZHA; default managed range is conservative (`1–30`) and configurable in options.
- Expiration disables slots but does not clear/delete PINs.
- Private HA storage is not encrypted-at-rest protection against HA host/backups/admin compromise.

## Development validation

```bash
python -m compileall custom_components tests
pytest -q
ruff check .
```

The tests use lightweight fakes/mocks so they can run without a full Home Assistant development install.
