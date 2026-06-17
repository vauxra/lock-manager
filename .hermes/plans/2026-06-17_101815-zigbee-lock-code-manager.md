# Zigbee Lock Code Manager Home Assistant Integration Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after Micheal explicitly approves execution.

**Goal:** Build a new Home Assistant custom integration repo at `/mnt/mintData/git/lock-manager` that manages Zigbee lock user-code slots, with first-class support for Kwikset Zigbee locks via ZHA.

**Architecture:** Start as a HACS-compatible custom integration named `zigbee_lock_manager` that wraps Home Assistant's existing ZHA lock-code actions instead of talking directly to zigpy clusters. The integration owns a local registry of labeled/named code slots, schedules/expiration metadata, validates Kwikset-safe PIN constraints, and exposes service actions for set/clear/enable/disable/sync while leaving actual lock/unlock entities owned by ZHA.

**Tech Stack:** Python 3.13-compatible Home Assistant custom component, ZHA service calls (`zha.set_lock_user_code`, `zha.clear_lock_user_code`, `zha.enable_lock_user_code`, `zha.disable_lock_user_code`), HA config flow/options flow, HA storage helper, pytest + `pytest-homeassistant-custom-component`, Ruff/pyright optional.

---

## Current Context / Assumptions

- Target repo path: `/mnt/mintData/git/lock-manager`.
- Repo does not exist yet; implementation will create it after approval.
- No code changes should happen before plan/grill approval; this plan file is the only created artifact so far.
- Minimum supported lock family: Kwikset Zigbee locks managed by Home Assistant ZHA.
- Home Assistant docs confirm ZHA exposes actions for lock user code operations:
  - `zha.set_lock_user_code`
  - `zha.clear_lock_user_code`
  - `zha.enable_lock_user_code`
  - `zha.disable_lock_user_code`
- HA's public ZHA service layer does not appear to expose a `get_lock_user_code`/slot discovery action like Z-Wave JS does.
- Zigpy's DoorLock cluster does expose lower-level commands such as `get_pin_code`, `get_user_status`, and lock attributes like `max_pin_len`; existing Keymaster/ZHA code uses lower-level cluster access for PIN reads, but support is device-dependent and should be treated as best-effort.
- Kwikset 954-style ZHA docs note `user_code` should be 4–8 digits. Plan will use 4–8 digits as MVP validation unless grill changes it.
- Recommended domain: `zigbee_lock_manager`.
- Recommended first version avoids a custom frontend panel/card; it exposes HA services plus stored registry/sensors so it is useful from scripts/automations/dashboards immediately.

## Existing Lock-Manager Research Notes

- Existing HA lock-code managers generally do **not** have true encrypted-at-rest PIN storage.
- Legacy/YAML lock managers commonly use `input_text` helpers, which expose PINs as HA entity state and are not acceptable for this integration.
- Modern lock managers commonly store recoverable PINs in HA config entries or HA `Store`; masking/redaction is mostly UI/API hygiene, not filesystem-level encryption.
- FutureTense Keymaster stores slot PINs in HA storage with reversible base64-style obfuscation and password-mode text entities; this is not encryption.
- `raman325/lock_code_manager` stores PINs in config-entry data/options, masks WebSocket output by default, and redacts diagnostics; useful UX pattern, but not where this integration should store PINs.
- `dmoralesdev/zha_lock_manager` encrypts codes with Fernet but stores the Fernet key in HA storage beside the data; this protects against casual reading of one file, not HA config/backups/admin compromise.
- Conclusion: use native HA private storage and strict redaction/masking; avoid `input_text`, config-entry PIN tables, entity-state PINs, and custom crypto theater unless HA gains a native/blessed secure-store primitive.

## Hubitat Lock-Manager Comparison Notes

- Reviewed exactly two Hubitat references: Hubitat's built-in Lock Code Manager docs and the community Reliable Locks app/thread.
- Hubitat Lock Code Manager attempts to import/retrieve existing codes on first run, but docs warn some locks do not export existing codes; for those, users should delete/re-enter codes through the manager so it becomes source of truth.
- Hubitat docs also highlight PIN length varies by device/keypad; keep PIN length configurable around the Kwikset 4–8 digit default.
- Hubitat Reliable Locks is not a code manager, but its useful pattern is command reliability wrapping: after issuing a lock command, refresh/check state and retry/report if the physical device did not reflect the desired state.
- Plan takeaway: add best-effort import/probe as a convenience only, keep local registry authoritative for manager-created codes, and track last operation status/retry errors so ZHA failures are visible instead of silent.

## Proposed MVP Behavior

1. User adds integration from UI config flow.
2. Integration lets user choose one or more existing ZHA lock entities/devices to manage.
3. Integration stores a code-slot registry in HA storage, per lock:
   - lock entity/device identifier
   - slot number
   - friendly name / person label plus optional tags/labels
   - recallable/editable PIN material stored only in a private HA storage file
   - safe metadata such as code length/fingerprint for diagnostics without revealing PINs
   - enabled/disabled state as last-known intent
   - scheduling metadata such as starts_at, expires_at, days/time windows, and notes
   - last operation status/error timestamp for audit and troubleshooting
4. Integration exposes service actions:
   - `zigbee_lock_manager.set_code`
   - `zigbee_lock_manager.clear_code`
   - `zigbee_lock_manager.enable_code`
   - `zigbee_lock_manager.disable_code`
   - `zigbee_lock_manager.sync_registry` / `apply_registry`
5. Services call through to the matching ZHA service for each target lock.
6. Integration creates diagnostic/sensor-ish entities only for safe metadata, for example:
   - managed lock count
   - occupied slot count
   - per-lock registry summary attributes without exposing PINs
7. Failure handling is conservative:
   - validate inputs before calling ZHA
   - surface clear HA log messages and service-call exceptions when ZHA rejects a request
   - do not silently mutate registry as successful unless the ZHA service call returns without error
   - record last operation status and retry/surface failed enable/disable operations, especially scheduled expiration disables

## Out of Scope for MVP Unless Grill Changes It

- Direct zigpy/ZHA cluster writes outside Home Assistant's public ZHA actions.
- Custom Lovelace card or frontend panel.
- Multi-platform support for Zigbee2MQTT or Z-Wave JS.
- Advanced scheduling UI/policy engine beyond basic MVP starts/expires/time-window fields.
- Reading existing codes back from locks. Many locks do not expose PINs safely/reliably; the registry should be intent/source-of-truth, not a guaranteed physical-lock readback.
- Guaranteed automatic slot discovery. MVP may include a best-effort probe if ZHA/zigpy cluster access is available, but the manager must work with manual/configurable slot ranges.
- Exposing PINs as plaintext outside the dedicated private code store.
- Cloud sync or remote account features.

## Files Likely to Change / Be Created

- Create: `/mnt/mintData/git/lock-manager/README.md`
- Create: `/mnt/mintData/git/lock-manager/AI-DECLARATION.md`
- Create: `/mnt/mintData/git/lock-manager/LICENSE`
- Create: `/mnt/mintData/git/lock-manager/.gitignore`
- Create: `/mnt/mintData/git/lock-manager/pyproject.toml`
- Create: `/mnt/mintData/git/lock-manager/hacs.json`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/__init__.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/manifest.json`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/const.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/config_flow.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/services.yaml`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/manager.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/storage.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/scheduler.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/sensor.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/diagnostics.py`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/strings.json`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/translations/en.json`
- Create: `/mnt/mintData/git/lock-manager/tests/conftest.py`
- Create: `/mnt/mintData/git/lock-manager/tests/test_config_flow.py`
- Create: `/mnt/mintData/git/lock-manager/tests/test_services.py`
- Create: `/mnt/mintData/git/lock-manager/tests/test_storage.py`
- Create: `/mnt/mintData/git/lock-manager/tests/test_scheduler.py`
- Create: `/mnt/mintData/git/lock-manager/tests/test_validation.py`

## Step-by-Step Plan

### Task 1: Create repo skeleton only after approval

**Objective:** Initialize a clean, testable HACS-style custom integration repository.

**Files:**
- Create: `/mnt/mintData/git/lock-manager/.gitignore`
- Create: `/mnt/mintData/git/lock-manager/pyproject.toml`
- Create: `/mnt/mintData/git/lock-manager/README.md`
- Create: `/mnt/mintData/git/lock-manager/AI-DECLARATION.md`
- Create: `/mnt/mintData/git/lock-manager/hacs.json`
- Create: `/mnt/mintData/git/lock-manager/custom_components/zigbee_lock_manager/manifest.json`

**AI disclosure requirements:**
- Add the AI-DECLARATION badge as the first visible line of `README.md`:
  ```markdown
  [![AI-DECLARATION: copilot](https://img.shields.io/badge/䷼%20AI--DECLARATION-copilot-fee2e2?labelColor=fee2e2)](https://ai-declaration.md)
  ```
- Create `AI-DECLARATION.md` using https://ai-declaration.md/en/0.1.2/.
- Use `level: copilot` as the highest AI usage level unless implementation becomes fully autonomous enough to require `auto`.
- Include process levels for design, implementation, testing, documentation, and review.

**Draft `AI-DECLARATION.md`:**
```markdown
---
version: "0.1.2"
level: copilot
processes:
  design: copilot
  implementation: copilot
  testing: copilot
  documentation: copilot
  review: copilot
---

This format is based on [AI-DECLARATION.md](https://ai-declaration.md/en/0.1.2/).

## Notes

- AI agents were used to plan, implement, test, document, and review this Home Assistant custom integration under human direction.
- The human maintainer approved the implementation direction and retains responsibility for reviewing behavior, security posture, and releases.
```

**Verification:**
- `python -m compileall custom_components tests`
- `python -m pytest --collect-only`

### Task 2: Add constants and validation helpers

**Objective:** Define domain constants, service names, storage keys, and Kwikset-safe validation.

**Files:**
- Create: `custom_components/zigbee_lock_manager/const.py`
- Add tests: `tests/test_validation.py`

**Validation rules for MVP:**
- code slot is positive integer, default allowed range TBD by grill
- user code is string of digits
- user code length is 4–8 digits for Kwikset Zigbee default
- user-facing name is non-empty when registry entry is created

**Verification:**
- `pytest tests/test_validation.py -v`

### Task 3: Implement config flow

**Objective:** Let HA users add the integration from UI and choose the initial ZHA lock targets.

**Files:**
- Create: `custom_components/zigbee_lock_manager/config_flow.py`
- Create/update: `custom_components/zigbee_lock_manager/strings.json`
- Create/update: `custom_components/zigbee_lock_manager/translations/en.json`
- Add tests: `tests/test_config_flow.py`

**Design:**
- Require config flow in `manifest.json` with `"config_flow": true`.
- First pass may allow empty target list and rely on service calls by `entity_id`, but preferred UX is lock selector during setup if HA selector APIs make this clean.

**Verification:**
- `pytest tests/test_config_flow.py -v`

### Task 4: Implement private storage-backed registry

**Objective:** Store code-slot metadata plus recallable/editable PIN material under native HA storage with predictable migration/versioning and strict redaction.

**Files:**
- Create: `custom_components/zigbee_lock_manager/storage.py`
- Add tests: `tests/test_storage.py`

**Registry shape draft:**
```json
{
  "version": 1,
  "locks": {
    "lock.front_door": {
      "slots": {
        "1": {
          "name": "Micheal",
          "labels": ["household"],
          "enabled": true,
          "starts_at": null,
          "expires_at": null,
          "schedule": null,
          "code_length": 6,
          "code_fingerprint": "sha256:...",
          "has_private_code": true,
          "notes": "optional"
        }
      }
    }
  }
}
```

**Security stance:**
- Home Assistant does not currently appear to provide an official encrypted-at-rest vault/secret-store API for custom integration-managed mutable data.
- Use native HA storage: a normal metadata store for non-secret registry data plus a dedicated `homeassistant.helpers.storage.Store(..., private=True, atomic_writes=True)` for recallable PINs. `private=True` improves file permissions but is not encryption.
- Never store PINs in config-entry data/options, helpers, entity state, attributes, diagnostics, logs, traces, repairs, or events.
- Never expose plaintext PINs in sensor state/attributes or diagnostics.
- Mask codes everywhere by default; only reveal/edit through an explicit, user-initiated integration flow/service path.
- Keep fingerprint/length metadata for safe comparisons and diagnostics.
- Redact `code`, `pin`, `user_code`, encrypted/private fields, and derived secrets everywhere.
- Do not add custom crypto in MVP unless HA provides a native/blessed secure store; avoid storing a reversible encryption key next to the data and pretending that meaningfully changes the threat model.

**Verification:**
- `pytest tests/test_storage.py -v`

### Task 4b: Implement scheduling engine

**Objective:** Apply starts/expires/time-window rules for managed codes without relying on separate HA automations.

**Files:**
- Create: `custom_components/zigbee_lock_manager/scheduler.py`
- Add tests: `tests/test_scheduler.py`

**Design:**
- Store label and schedule metadata per slot.
- Support at least `starts_at`, `expires_at`, and enabled/disabled desired state in MVP.
- Optional simple recurring windows may be included if they stay small and testable.
- On HA start/reload, reconcile all schedules and enqueue any overdue enable/disable actions.
- Expiration policy: disable the slot only; do not clear/delete the PIN from the lock or private registry automatically.
- Use Home Assistant async time helpers rather than ad-hoc sleep loops.

**Verification:**
- Tests cover not-yet-active codes, active codes, expired codes, HA restart/reload reconciliation, and no plaintext PIN leakage through scheduler logs/events.

### Task 5: Implement ZHA service adapter / manager

**Objective:** Centralize calls from this integration to HA's ZHA lock code actions.

**Files:**
- Create: `custom_components/zigbee_lock_manager/manager.py`
- Add tests: `tests/test_services.py`

**Mapping:**
- `set_code` -> `zha.set_lock_user_code`
- `clear_code` -> `zha.clear_lock_user_code`
- `enable_code` -> `zha.enable_lock_user_code`
- `disable_code` -> `zha.disable_lock_user_code`

**Verification:**
- Unit tests patch `hass.services.async_call` and assert exact domain/service/payload.
- Include failure tests: validation failure does not call ZHA; ZHA exception does not update registry as successful.

### Task 6: Register public integration services

**Objective:** Expose stable, documented HA service actions for code management.

**Files:**
- Create/update: `custom_components/zigbee_lock_manager/__init__.py`
- Create/update: `custom_components/zigbee_lock_manager/services.yaml`
- Add/update tests: `tests/test_services.py`

**Draft service schemas:**
- `set_code`:
  - `entity_id` lock entity selector
  - `slot` integer
  - `name` text
  - `labels` list/string selector
  - `code` text/password-style field
  - `enabled` boolean default true
  - `starts_at` datetime optional
  - `expires_at` datetime optional
  - `schedule` optional simple recurring schedule object/string if implemented in MVP
- `clear_code`:
  - `entity_id`
  - `slot`
- `enable_code` / `disable_code`:
  - `entity_id`
  - `slot`
- `sync_registry`:
  - optional `entity_id`
- `apply_schedules`:
  - optional `entity_id`
  - reconciles due/expired slots immediately
- `probe_slots`:
  - optional `entity_id`
  - optional slot range
  - best-effort lower-level ZHA/zigpy read/import helper; failure must not block normal registry-based management

**Verification:**
- `pytest tests/test_services.py -v`
- Manual later: call HA service from Developer Tools against a test/dev HA instance.

### Task 7: Add safe sensor/diagnostics surface

**Objective:** Make integration state visible without leaking PINs.

**Files:**
- Create: `custom_components/zigbee_lock_manager/sensor.py`
- Create: `custom_components/zigbee_lock_manager/diagnostics.py`
- Add tests if feasible.

**Design:**
- One summary sensor per config entry or per managed lock.
- Attributes may include slot numbers and names, but not plaintext codes or hashes unless explicitly useful and safe.
- Diagnostics redacts any field that could contain a code.

**Verification:**
- Tests assert sensor attributes/diagnostics do not include `code` plaintext.
- Tests assert operation status/error attributes never include plaintext PINs.

### Task 8: Documentation and examples

**Objective:** Give Micheal copy-pasteable setup/service examples.

**Files:**
- Update: `README.md`

**Include:**
- AI-DECLARATION copilot badge as the first visible line of the README.
- HACS/custom_components install instructions
- HA restart/setup steps
- Kwikset/ZHA assumptions
- Example service calls for set/clear/enable/disable
- Security warning about PIN storage/logs/backups
- Known limitations and non-goals

**Verification:**
- README examples match `services.yaml` schema and tests.

### Task 9: Local validation pass

**Objective:** Prove the repo is not just pretty scaffolding, darling — it actually loads and tests.

**Commands:**
```bash
cd /mnt/mintData/git/lock-manager
python -m compileall custom_components tests
pytest -q
ruff check .
```

**Expected:**
- compileall succeeds
- pytest passes
- ruff passes or known style exceptions are fixed

### Task 10: Optional live HA smoke test

**Objective:** Validate against a real Home Assistant dev/container instance and a test ZHA lock if available.

**Steps:**
- Copy or mount `custom_components/zigbee_lock_manager` into HA config.
- Restart HA.
- Add integration through Settings -> Devices & services.
- Call `zigbee_lock_manager.set_code` against a Kwikset ZHA lock test slot.
- Verify the code works physically or via ZHA device response/logs.

**Safety:**
- Use a non-critical test slot.
- Do not overwrite known working household access slots without explicit slot mapping.

## Tests / Validation Strategy

- Unit tests for validation and redaction.
- Unit tests for service schemas and ZHA call payloads.
- Config-flow tests for setup paths and duplicate-entry handling.
- Storage tests for save/load/migration, private-store isolation, masking, and redaction behavior.
- Scheduler tests for starts/expires behavior, restart reconciliation, and overdue handling.
- Optional integration smoke test in HA dev environment.
- Optional physical Kwikset lock test only after slot/code safety is agreed.

## Risks / Tradeoffs

- **ZHA service API dependency:** Wrapping public ZHA actions is safer than direct zigpy calls but depends on ZHA service names/payloads staying stable.
- **Readback limitations:** Zigbee locks may not reliably reveal existing PINs; the registry is a manager/source-of-intent, not guaranteed device truth.
- **PIN storage:** Home Assistant appears to offer private file permissions/redaction patterns, not a built-in encrypted-at-rest custom integration vault. MVP will use native HA private storage, strict redaction, masked display by default, and a documented trust boundary that HA host/backups/admin access can access secrets.
- **Slot limits vary:** Kwikset models can differ. Need configurable max slot or conservative default.
- **Slot discovery:** Z-Wave JS exposes a get-usercode action, but ZHA does not appear to expose equivalent public HA services. Lower-level ZHA/zigpy reads may work on some locks but should be optional/best-effort, not required for core management.
- **Frontend UX:** Service-first MVP is fast and robust, but less friendly than a custom card/panel.
- **Physical lock testing risk:** Bad slot choices can lock people out or overwrite working codes.
- **Scheduling reliability:** Expiring access is safety/security-sensitive. MVP expiration policy is disable-only, with restart reconciliation and retry/error reporting if ZHA disable fails.

## Grill Decisions / Open Questions

- Grill decision: MVP UX is service-first: HA services + stored registry + safe summary sensor; defer custom Lovelace/frontend UI to v2.
- Grill decision: PINs must be recallable/editable using native HA structures: store them only in a dedicated private HA storage file, redact everywhere, mask by default, and do not implement custom crypto unless HA has a native secure-store primitive.
- Grill decision: Slot management uses a manual/configurable range as the reliable base; default to a conservative range, never assume unknown slots are empty, and treat lower-level ZHA/zigpy slot probing as optional/best-effort.
- Grill decision: Scheduling/expiration and labels are MVP defaults, not v2-only.
- Grill decision: Expiration disables slots only; it does not clear/delete PINs from the lock or private registry automatically.
- Grill decision: Target Micheal's current Home Assistant version baseline: 2026.2.2.
- Grill decision: Execute with subagent-driven-development task-by-task, with spec-compliance and code-quality review gates before moving between major chunks.
- Grill decision: Include `AI-DECLARATION.md` v0.1.2 in the repo and put the matching `copilot` badge at the top of `README.md`; raise to `auto` only if execution becomes fully autonomous beyond the current human-approved subagent workflow.
- Safety decision during implementation: do not perform any live lock mutation tests against Micheal's current lock/codes. Until explicitly approved later, validation must be local/unit-test only with mocks/fakes; no real set/edit/clear/remove/disable calls against the physical lock.

## Recommended Defaults Before Grill

- Use `zigbee_lock_manager` as integration domain.
- Build HACS-compatible custom integration first, not core HA PR.
- Target ZHA only for MVP; leave Zigbee2MQTT/Z-Wave JS as future adapters.
- Target Home Assistant 2026.2.2 as the baseline, matching Micheal's current `homeassistant` container on `tool-server`.
- Store recallable/editable PINs only in a dedicated private HA storage file; mask by default and redact everywhere.
- Validate Kwikset codes as 4–8 digits.
- Expose service actions first, including labels and scheduling fields; defer custom frontend.
- Use subagent-driven-development after grill because this is multi-file integration work with test/review gates.
