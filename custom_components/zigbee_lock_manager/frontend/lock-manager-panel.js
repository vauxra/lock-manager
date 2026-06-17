class ZigbeeLockManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._summary = null;
    this._error = "";
    this._busy = false;
    this._loaded = false;
    this._revealedPins = new Map();
    this._draft = {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  connectedCallback() {
    this._render();
  }

  async _load() {
    if (!this._hass) return;
    this._busy = true;
    this._error = "";
    this._render();
    try {
      this._summary = await this._hass.callWS({ type: "zigbee_lock_manager/summary" });
    } catch (err) {
      this._error = this._errorText(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _errorText(err) {
    if (!err) return "Unknown error";
    if (typeof err === "string") return err;
    return err.message || err.error || JSON.stringify(err);
  }

  _bounds() {
    return this._summary?.bounds || {
      min_slot: 1,
      max_slot: 30,
      min_code_length: 4,
      max_code_length: 8,
    };
  }

  _slotCount() {
    const bounds = this._bounds();
    return Math.max(0, bounds.max_slot - bounds.min_slot + 1);
  }

  _locks() {
    const locks = new Set(this._summary?.lock_entities || []);
    Object.keys(this._summary?.locks || {}).forEach((entityId) => locks.add(entityId));
    return [...locks].sort();
  }

  _allLockEntities() {
    const locks = new Set(this._locks());
    Object.keys(this._hass?.states || {})
      .filter((entityId) => entityId.startsWith("lock."))
      .forEach((entityId) => locks.add(entityId));
    if (this._draft.entity_id) locks.add(this._draft.entity_id);
    return [...locks].sort();
  }

  _entityLabel(entityId) {
    const state = this._hass?.states?.[entityId];
    const name = state?.attributes?.friendly_name;
    return name ? `${name} (${entityId})` : entityId;
  }

  _pinKey(entityId, slot) {
    return `${entityId}::${slot}`;
  }

  async _call(service, data, successMessage = "Done") {
    this._busy = true;
    this._error = "";
    this._render();
    try {
      await this._hass.callService("zigbee_lock_manager", service, data);
      this._toast(successMessage);
      await this._load();
    } catch (err) {
      this._error = this._errorText(err);
      this._busy = false;
      this._render();
    }
  }

  _toast(message) {
    this.dispatchEvent(
      new CustomEvent("hass-notification", {
        bubbles: true,
        composed: true,
        detail: { message },
      }),
    );
  }

  _captureDraft() {
    const root = this.shadowRoot;
    const draft = { ...this._draft };
    for (const id of ["entity_id", "slot", "name", "code", "labels", "starts_at", "expires_at"]) {
      const element = root.getElementById(id);
      if (element) draft[id] = element.value;
    }
    const enabled = root.getElementById("enabled");
    if (enabled) draft.enabled = enabled.checked;
    draft.activeElementId = root.activeElement?.id || "";
    this._draft = draft;
    return draft;
  }

  _restoreDraft(draft = this._draft) {
    const root = this.shadowRoot;
    for (const id of ["entity_id", "slot", "name", "code", "labels", "starts_at", "expires_at"]) {
      const element = root.getElementById(id);
      if (element && draft[id] !== undefined) element.value = draft[id];
    }
    const enabled = root.getElementById("enabled");
    if (enabled && draft.enabled !== undefined) enabled.checked = draft.enabled;
    const active = draft.activeElementId ? root.getElementById(draft.activeElementId) : null;
    if (active && document.activeElement !== active) active.focus();
  }

  _formData() {
    const root = this.shadowRoot;
    const labels = root.getElementById("labels")?.value || "";
    const startsAt = root.getElementById("starts_at")?.value || "";
    const expiresAt = root.getElementById("expires_at")?.value || "";
    const data = {
      entity_id: root.getElementById("entity_id")?.value?.trim(),
      slot: Number(root.getElementById("slot")?.value),
      name: root.getElementById("name")?.value?.trim(),
      code: root.getElementById("code")?.value,
      enabled: root.getElementById("enabled")?.checked ?? true,
    };
    if (labels.trim()) data.labels = labels.split(",").map((item) => item.trim()).filter(Boolean);
    if (startsAt) data.starts_at = new Date(startsAt).toISOString();
    if (expiresAt) data.expires_at = new Date(expiresAt).toISOString();
    return data;
  }

  _validateSetData(data) {
    const bounds = this._bounds();
    if (!data.entity_id) return "Choose or type a lock entity.";
    if (!Number.isInteger(data.slot)) return "Slot must be a number.";
    if (data.slot < bounds.min_slot || data.slot > bounds.max_slot) {
      return `Slot must be between ${bounds.min_slot} and ${bounds.max_slot}.`;
    }
    if (!data.name) return "Name is required.";
    if (!/^\d+$/.test(data.code || "")) return "PIN must contain digits only.";
    if (data.code.length < bounds.min_code_length || data.code.length > bounds.max_code_length) {
      return `PIN must be ${bounds.min_code_length}-${bounds.max_code_length} digits.`;
    }
    return "";
  }

  async _submitSet(event) {
    event.preventDefault();
    const data = this._formData();
    const validationError = this._validateSetData(data);
    if (validationError) {
      this._error = validationError;
      this._render();
      return;
    }
    await this._call("set_code", data, `Stored slot ${data.slot}`);
    const code = this.shadowRoot.getElementById("code");
    if (code) code.value = "";
    this._draft.code = "";
  }

  async _slotAction(service, entityId, slot) {
    await this._call(service, { entity_id: entityId, slot }, `${service.replace("_", " ")} slot ${slot}`);
  }

  async _clearAll(entityId) {
    const bounds = this._bounds();
    const count = this._slotCount();
    const first = confirm(
      `Clear ALL configured slots ${bounds.min_slot}-${bounds.max_slot} (${count} slots) on ${entityId}?\n\nThis can remove working lock codes from the physical lock.`,
    );
    if (!first) return;
    const typed = prompt(`Type CLEAR to confirm clearing slots ${bounds.min_slot}-${bounds.max_slot} on ${entityId}.`);
    if (typed !== "CLEAR") return;
    await this._call(
      "clear_all_codes",
      {
        entity_id: entityId,
        start_slot: bounds.min_slot,
        end_slot: bounds.max_slot,
        known_only: false,
      },
      `Clear-all sent for ${entityId}`,
    );
  }

  async _clearKnown(entityId) {
    const managedCount = Object.keys(this._summary?.locks?.[entityId]?.slots || {}).length;
    if (!managedCount) {
      this._error = `No managed slots are recorded for ${entityId}.`;
      this._render();
      return;
    }
    const ok = confirm(
      `Clear ${managedCount} known managed slot${managedCount === 1 ? "" : "s"} on ${entityId}?\n\nThis only clears slots currently recorded in the Lock Codes registry.`,
    );
    if (!ok) return;
    await this._call(
      "clear_all_codes",
      {
        entity_id: entityId,
        known_only: true,
      },
      `Clear-known sent for ${entityId}`,
    );
  }

  async _revealPin(entityId, slot) {
    const key = this._pinKey(entityId, slot);
    if (this._revealedPins.has(key)) {
      this._revealedPins.delete(key);
      this._render();
      return;
    }
    this._busy = true;
    this._error = "";
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "zigbee_lock_manager/private_code",
        entity_id: entityId,
        slot,
      });
      if (!result?.code) {
        this._error = `No private PIN stored for slot ${slot}.`;
      } else {
        this._revealedPins.set(key, result.code);
      }
    } catch (err) {
      this._error = this._errorText(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _setEntity(entityId, slot = "") {
    const entity = this.shadowRoot.getElementById("entity_id");
    const slotInput = this.shadowRoot.getElementById("slot");
    if (entity) entity.value = entityId;
    if (slotInput && slot !== "") slotInput.value = slot;
  }

  _renderPinControl(entityId, slot, meta) {
    const key = this._pinKey(entityId, slot);
    const revealed = this._revealedPins.get(key);
    const placeholder = meta.has_private_code ? "••••••" : "No stored PIN";
    const value = revealed || "";
    const buttonLabel = revealed ? "🙈" : "👁";
    return `
      <div class="pin-line">
        <input class="pin-field" type="${revealed ? "text" : "password"}" readonly value="${this._esc(value)}" placeholder="${placeholder}">
        <button class="icon" title="${revealed ? "Hide PIN" : "Reveal PIN"}" data-pin="${entityId}" data-slot="${slot}" ${meta.has_private_code ? "" : "disabled"}>${buttonLabel}</button>
      </div>`;
  }

  _renderSlots(entityId, lock) {
    const slots = Object.entries(lock?.slots || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
    if (!slots.length) return `<p class="muted">No managed slots yet.</p>`;
    return `
      <div class="table">
        <div class="row header">
          <span>Slot</span><span>Name</span><span>Status / PIN</span><span>Schedule</span><span>Last op</span><span>Actions</span>
        </div>
        ${slots.map(([slotText, meta]) => {
          const slot = Number(slotText);
          const labels = (meta.labels || []).join(", ");
          const enabled = meta.enabled ? "Enabled" : "Disabled";
          const privateCode = meta.has_private_code ? `${meta.code_length || "?"} digit PIN stored` : "No private PIN";
          const schedule = [
            meta.starts_at ? `starts ${this._fmtDate(meta.starts_at)}` : "",
            meta.expires_at ? `expires ${this._fmtDate(meta.expires_at)}` : "",
          ].filter(Boolean).join(" · ") || "—";
          const last = meta.last_operation
            ? `${meta.last_operation.operation || "op"}: ${meta.last_operation.status || "?"}`
            : "—";
          return `
            <div class="row">
              <span><button class="link" data-fill="${entityId}" data-slot="${slot}">${slot}</button></span>
              <span><strong>${this._esc(meta.name || `Slot ${slot}`)}</strong>${labels ? `<small>${this._esc(labels)}</small>` : ""}</span>
              <span><span class="pill ${meta.enabled ? "ok" : "off"}">${enabled}</span><small>${privateCode}</small>${this._renderPinControl(entityId, slot, meta)}</span>
              <span>${this._esc(schedule)}</span>
              <span>${this._esc(last)}</span>
              <span class="actions">
                <button data-action="enable_code" data-entity="${entityId}" data-slot="${slot}">Enable</button>
                <button data-action="disable_code" data-entity="${entityId}" data-slot="${slot}">Disable</button>
                <button class="danger" data-action="clear_code" data-entity="${entityId}" data-slot="${slot}">Clear</button>
              </span>
            </div>`;
        }).join("")}
      </div>`;
  }

  _fmtDate(value) {
    try {
      return new Date(value).toLocaleString();
    } catch (_err) {
      return value;
    }
  }

  _esc(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    }[char]));
  }

  _render() {
    const draft = this._captureDraft();
    const bounds = this._bounds();
    const slotCount = this._slotCount();
    const locks = this._locks();
    const lockOptions = this._allLockEntities();
    const managedLocks = this._summary?.locks || {};
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 24px; color: var(--primary-text-color); }
        .wrap { max-width: 1240px; margin: 0 auto; }
        h1 { margin: 0 0 4px; font-size: 28px; }
        h2 { margin-top: 0; }
        .muted, small { color: var(--secondary-text-color); display: block; }
        .grid { display: grid; grid-template-columns: minmax(320px, 420px) 1fr; gap: 18px; align-items: start; }
        .card { background: var(--card-background-color); border-radius: 14px; padding: 18px; box-shadow: var(--ha-card-box-shadow, 0 2px 10px rgba(0,0,0,.12)); border: 1px solid var(--divider-color); }
        label { display: block; font-size: 13px; color: var(--secondary-text-color); margin: 10px 0 4px; }
        input, select { box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid var(--divider-color); border-radius: 8px; background: var(--card-background-color); color: var(--primary-text-color); }
        input[type="checkbox"] { width: auto; }
        button { cursor: pointer; border: 0; border-radius: 8px; padding: 9px 12px; background: var(--primary-color); color: var(--text-primary-color, white); margin: 2px; }
        button:disabled { cursor: not-allowed; opacity: .45; }
        button.secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
        button.caution { background: rgba(219,68,55,.14); color: var(--error-color, #db4437); border: 1px solid rgba(219,68,55,.45); }
        button.danger { background: var(--error-color, #db4437); color: white; }
        button.link { background: none; color: var(--primary-color); padding: 0; text-decoration: underline; }
        button.icon { min-width: 40px; padding: 8px; }
        .topbar { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 18px; }
        .error { background: rgba(219,68,55,.12); border: 1px solid var(--error-color, #db4437); padding: 10px; border-radius: 8px; margin: 12px 0; }
        .hint { background: rgba(3,169,244,.10); border: 1px solid rgba(3,169,244,.35); padding: 10px; border-radius: 8px; margin: 12px 0; }
        .table { display: grid; gap: 0; overflow-x: auto; }
        .row { display: grid; grid-template-columns: 60px minmax(150px, 1.2fr) minmax(190px, 1.1fr) minmax(160px, 1fr) minmax(120px, .9fr) minmax(220px, auto); gap: 8px; align-items: center; padding: 10px 0; border-top: 1px solid var(--divider-color); min-width: 1030px; }
        .row.header { color: var(--secondary-text-color); font-size: 12px; text-transform: uppercase; border-top: 0; }
        .pill { display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 12px; margin-bottom: 3px; }
        .pill.ok { background: rgba(15,157,88,.14); color: var(--success-color, #0f9d58); }
        .pill.off { background: rgba(128,128,128,.16); color: var(--secondary-text-color); }
        .actions { white-space: nowrap; }
        .lock-card { margin-bottom: 16px; }
        .lock-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
        .bulk-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .pin-line { display: flex; gap: 6px; margin-top: 5px; }
        .pin-field { min-width: 0; padding: 8px; font-family: monospace; }
        @media (max-width: 900px) { :host { padding: 12px; } .grid { grid-template-columns: 1fr; } .topbar, .lock-head { align-items: flex-start; flex-direction: column; } }
      </style>
      <div class="wrap">
        <div class="topbar">
          <div>
            <h1>Lock Codes</h1>
            <div class="muted">Manage Zigbee lock code slots. PINs are masked and only revealed on explicit admin click.</div>
            <div class="muted">Configured slots: ${bounds.min_slot}-${bounds.max_slot} (${slotCount} total). Public ZHA does not reliably report the lock's physical max slot count.</div>
          </div>
          <button class="secondary" id="refresh">${this._busy ? "Working…" : "Refresh"}</button>
        </div>
        ${this._error ? `<div class="error">${this._esc(this._error)}</div>` : ""}
        <div class="grid">
          <form class="card" id="set-form">
            <h2>Set / update code</h2>
            <label for="entity_id">Lock entity</label>
            <select id="entity_id" required>
              <option value="">Choose a lock…</option>
              ${lockOptions.map((lock) => `<option value="${this._esc(lock)}">${this._esc(this._entityLabel(lock))}</option>`).join("")}
            </select>
            <div class="form-row">
              <div><label for="slot">Slot</label><input id="slot" type="number" min="${bounds.min_slot}" max="${bounds.max_slot}" value="${bounds.min_slot}" required></div>
              <div><label for="name">Name</label><input id="name" placeholder="Guest / Housekeeper" required></div>
            </div>
            <label for="code">PIN (${bounds.min_code_length}-${bounds.max_code_length} digits)</label>
            <input id="code" type="password" inputmode="numeric" pattern="\\d*" autocomplete="new-password" required>
            <label for="labels">Labels, comma-separated</label>
            <input id="labels" placeholder="guest, test">
            <label for="starts_at">Starts at</label>
            <input id="starts_at" type="datetime-local">
            <label for="expires_at">Expires at</label>
            <input id="expires_at" type="datetime-local">
            <label><input id="enabled" type="checkbox" checked> Enabled now</label>
            <div class="hint">Use a known safe/unoccupied slot first. This UI sends <code>entity_id</code> under service <code>data</code>.</div>
            <button type="submit">Save code</button>
          </form>
          <div>
            ${(locks.length ? locks : [""]).map((entityId) => entityId ? `
              <section class="card lock-card">
                <div class="lock-head">
                  <div>
                    <h2>${this._esc(entityId)}</h2>
                    <div class="muted">Slot coverage: ${bounds.min_slot}-${bounds.max_slot} (${slotCount} configured)</div>
                  </div>
                  <div class="bulk-actions">
                    <button class="caution" data-clear-known="${entityId}">Clear known managed</button>
                    <button class="danger" data-clear-all="${entityId}">Clear all ${bounds.min_slot}-${bounds.max_slot}</button>
                  </div>
                </div>
                ${this._renderSlots(entityId, managedLocks[entityId])}
              </section>` : `
              <section class="card">
                <h2>No managed lock codes yet</h2>
                <p class="muted">Add a code with the form. If your configured lock does not appear, type its entity ID directly.</p>
              </section>`).join("")}
          </div>
        </div>
      </div>`;

    this.shadowRoot.getElementById("refresh")?.addEventListener("click", () => this._load());
    this.shadowRoot.getElementById("set-form")?.addEventListener("submit", (event) => this._submitSet(event));
    this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const service = button.getAttribute("data-action");
        const entityId = button.getAttribute("data-entity");
        const slot = Number(button.getAttribute("data-slot"));
        if (service === "clear_code" && !confirm(`Clear slot ${slot} on ${entityId}?`)) return;
        this._slotAction(service, entityId, slot);
      });
    });
    this.shadowRoot.querySelectorAll("[data-fill]").forEach((button) => {
      button.addEventListener("click", () => this._setEntity(button.getAttribute("data-fill"), button.getAttribute("data-slot")));
    });
    this.shadowRoot.querySelectorAll("[data-pin]").forEach((button) => {
      button.addEventListener("click", () => this._revealPin(button.getAttribute("data-pin"), Number(button.getAttribute("data-slot"))));
    });
    this.shadowRoot.querySelectorAll("[data-clear-all]").forEach((button) => {
      button.addEventListener("click", () => this._clearAll(button.getAttribute("data-clear-all")));
    });
    this.shadowRoot.querySelectorAll("[data-clear-known]").forEach((button) => {
      button.addEventListener("click", () => this._clearKnown(button.getAttribute("data-clear-known")));
    });
    this._restoreDraft(draft);
  }
}

customElements.define("zigbee-lock-manager-panel", ZigbeeLockManagerPanel);
