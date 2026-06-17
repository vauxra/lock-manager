# Rubber Duck Review Brief: Zigbee Lock Manager

You are reviewing this repository as an independent code reviewer. Treat this file as the orientation prompt for a careful technical and security review.

## What this repo is

`lock-manager` is a Home Assistant custom integration named **Zigbee Lock Manager**. It lives under:

```text
custom_components/zigbee_lock_manager/
```

The integration is intended to manage Zigbee door-lock user-code slots, with the MVP focused on **Kwikset Zigbee locks paired through ZHA**.

This is not a frontend-polish-first project. The current goal is a Home Assistant integration with a practical sidebar panel, safe backend behavior, private PIN storage, redacted metadata, scheduling, tests, and clear docs.

## Stated goals

The repository aims to provide:

1. A HACS-style Home Assistant custom integration.
2. Home Assistant services for lock code management:
   - `zigbee_lock_manager.set_code`
   - `zigbee_lock_manager.clear_code`
   - `zigbee_lock_manager.enable_code`
   - `zigbee_lock_manager.disable_code`
   - `zigbee_lock_manager.apply_registry`
   - `zigbee_lock_manager.sync_registry`
   - `zigbee_lock_manager.apply_schedules`
   - `zigbee_lock_manager.probe_slots`
3. A Home Assistant sidebar panel named **Lock Codes** that lets administrators see managed slots and set, clear, enable, or disable codes without YAML.
4. ZHA-backed lock operations using public ZHA services:
   - `zha.set_lock_user_code`
   - `zha.clear_lock_user_code`
   - `zha.enable_lock_user_code`
   - `zha.disable_lock_user_code`
5. Safe local registry behavior:
   - plaintext PINs only in a dedicated Home Assistant private `Store(..., private=True, atomic_writes=True)` storage file;
   - no plaintext PINs in config entries, options, helpers, entity states/attributes, diagnostics, logs, events, traces, repairs, or public metadata;
   - no brute-forceable PIN fingerprints in public metadata.
6. A safe metadata registry that can expose only redacted or non-secret information:
   - entity ID;
   - slot;
   - redacted name/labels/notes/schedule metadata;
   - desired enabled state;
   - starts/expires timestamps;
   - PIN length;
   - private-code presence;
   - last operation status/error/timestamp.
7. Scheduling semantics:
   - future `starts_at` codes should not become usable early;
   - expired `expires_at` codes should be disabled, not cleared/deleted;
   - expiration must preserve private PINs for audit/reapply/manual decisions;
   - restart/reload reconciliation should apply current schedule intent.
8. A conservative `probe_slots` behavior:
   - public ZHA does not provide reliable readback of lock user codes;
   - probing should not assume slots are empty;
   - probing should not expose, request, or infer PINs.
9. Lightweight local tests that do not require a full Home Assistant install or physical lock.

## Important safety boundaries

Do **not** call real Home Assistant, ZHA, or physical lock services during review unless the human maintainer explicitly approves it. Review and test locally with mocks/fakes only.

Do **not** introduce code that clears, disables, overwrites, or mutates real lock slots as part of tests, diagnostics, import, discovery, or probing.

Do **not** move PINs into Home Assistant config entries/options, entity attributes, diagnostics, logs, events, traces, repairs, or public metadata.

Do **not** add frontend polish at the expense of backend correctness. The sidebar panel must preserve the same PIN-safety boundaries as the services.

## Review task

Perform a code review of this repository. Look for correctness, security, Home Assistant integration quality, and maintainability issues. If you are allowed to edit, make focused improvements with tests. If you are only reviewing, produce findings with severity and file/line references.

Prioritize these review areas:

### Security and privacy

- Can any plaintext PIN leak into public metadata, sensors, diagnostics, logs, error messages, test output, README examples beyond intentional examples, or entity attributes?
- Are legacy/invalid public registry entries scrubbed safely on load?
- Are short numeric PINs protected from brute-forceable hashes/fingerprints in public state?
- Are service error paths redacted, especially when device/ZHA errors echo user codes?
- Are private-store APIs narrowly used and never returned to callers?

### Lock safety

- Can disabled, future, or expired codes become active by accident?
- Does `apply_registry` / `sync_registry` avoid reactivating expired or disabled codes?
- Does expiration disable only, without clearing/deleting private PINs?
- Does enabling a scheduled/future code program the private PIN only when it is supposed to become active?
- Are partial failures handled in ways that avoid silently granting access?

### Home Assistant correctness

- Does the integration follow expected custom integration structure?
- Are services registered once and dispatched to the current manager instance after reloads/options changes?
- Are config flow/options values actually used by runtime validation?
- Are storage writes async and appropriate for Home Assistant?
- Are diagnostics and sensors safe and useful?
- Is unload behavior clean?

### Validation and tests

- Are slot bounds and PIN length rules enforced consistently?
- Are tests meaningful and isolated from real HA/ZHA devices?
- Are schedule edge cases covered?
- Are failure paths covered?
- Do docs match behavior?

## Expected verification commands

Run these from the repo root after any change:

```bash
python -m compileall custom_components tests
pytest -q
ruff check .
```

If you add dependencies or change project config, explain why.

## Output requested from reviewers

Please report:

1. Verdict: approve / approve with nits / needs changes.
2. Critical findings, if any.
3. Important findings, if any.
4. Minor findings or polish, if any.
5. Changes made, if you edited files.
6. Verification commands run and their results.
7. Residual risks or assumptions.

Be concrete. Prefer file paths, function names, and specific failure scenarios over general advice.
