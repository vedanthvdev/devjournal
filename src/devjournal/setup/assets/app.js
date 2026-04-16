// SPDX-FileCopyrightText: 2026 Vedanth Vasudev
// SPDX-License-Identifier: MIT
//
// devjournal setup UI — single-page client. Talks to the local Python server
// over JSON. Every mutating request carries the CSRF token injected into
// <meta name="csrf-token"> at page render time.

(() => {
  "use strict";

  const CSRF_TOKEN = document
    .querySelector('meta[name="csrf-token"]')
    ?.getAttribute("content");

  const THEME_KEY = "devjournal-theme";

  // Secret-bearing collectors + the field under collectors.<name> that holds
  // the plaintext. Mirrors server._SECRET_CONFIG_KEYS so the two stay in sync.
  const SECRET_FIELDS = {
    jira: "api_token",
    confluence: "api_token",
    gitlab: "token",
    github: "token",
  };

  // ----- Theme handling -----

  const applyTheme = (theme) => {
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  };

  const initTheme = () => {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) applyTheme(stored);
    document.getElementById("theme-toggle").addEventListener("click", () => {
      const current =
        document.documentElement.getAttribute("data-theme") ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = current === "dark" ? "light" : "dark";
      localStorage.setItem(THEME_KEY, next);
      applyTheme(next);
    });
  };

  // ----- HTTP helpers -----

  const api = async (method, path, body) => {
    const headers = { "X-DevJournal-Token": CSRF_TOKEN };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const resp = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
    if (resp.status === 204) return null;
    const text = await resp.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON */ }
    if (!resp.ok) {
      const msg = (data && data.error) || `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    return data;
  };

  // ----- State -----

  const state = {
    config: {},
    secretsPresent: {},
    // Per-collector masked preview string (e.g. "••••••••wXyZ") or null when
    // no token is stored. Populated from the server on boot + after every
    // save. The plaintext never leaves the server — the preview is the only
    // way the UI can confirm "yes, your token is still saved" on revisit.
    secretsPreview: {},
    // Whether the OS has a working native folder picker (osascript on
    // macOS, zenity/kdialog on Linux). We probe on boot so we can hide the
    // Browse buttons on hosts where clicking them would just surface an
    // error, rather than showing disabled-looking buttons everywhere.
    folderPickerAvailable: false,
    keyringAvailable: false,
    version: "",
    dirtySecrets: {},  // collector -> plaintext (only tokens the user changed)
    pendingClears: new Set(),  // collectors the user clicked "Clear" on
  };

  // ----- Rendering helpers -----

  const el = (sel, root = document) => root.querySelector(sel);
  const els = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const setText = (selector, text) => {
    const node = el(selector);
    if (node) node.textContent = text;
  };

  // ----- Toasts -----
  //
  // A tiny stackable notification system. We replaced the single
  // always-on banner with this because (a) a static green "Authenticated"
  // line reads like an error in peripheral vision and (b) banners fight
  // the user for the top of the page. Toasts auto-dismiss, can be
  // dismissed manually, and never shift layout.
  //
  // Defaults: success/info toasts stay for 4 s; warn/err stay for 7 s so
  // there's time to read them. Callers can override with ``duration``.
  const _TOAST_ICONS = { ok: "✓", err: "✕", warn: "!", info: "i" };
  const _TOAST_DEFAULTS = { ok: 4000, info: 4000, warn: 7000, err: 7000 };

  const showToast = (message, kind = "info", opts = {}) => {
    const host = el("#toasts");
    if (!host) return null;
    const safeKind = _TOAST_ICONS[kind] ? kind : "info";
    const toast = document.createElement("div");
    toast.className = `toast ${safeKind}`;
    toast.setAttribute("role", safeKind === "err" ? "alert" : "status");

    const icon = document.createElement("span");
    icon.className = "toast-icon";
    icon.textContent = _TOAST_ICONS[safeKind];
    icon.setAttribute("aria-hidden", "true");

    const body = document.createElement("div");
    body.className = "toast-body";
    if (opts.title) {
      const t = document.createElement("div");
      t.className = "toast-title";
      t.textContent = opts.title;
      body.appendChild(t);
      const d = document.createElement("div");
      d.className = "toast-detail";
      d.textContent = message;
      body.appendChild(d);
    } else {
      body.textContent = message;
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Dismiss notification");
    close.textContent = "×";

    toast.append(icon, body, close);
    host.appendChild(toast);

    const dismiss = () => {
      if (toast.dataset.leaving === "1") return;
      toast.dataset.leaving = "1";
      toast.classList.add("leaving");
      // Keep in sync with toast-out animation duration in styles.css.
      setTimeout(() => toast.remove(), 200);
    };
    close.addEventListener("click", dismiss);

    const duration = opts.duration ?? _TOAST_DEFAULTS[safeKind];
    if (duration > 0) setTimeout(dismiss, duration);
    return dismiss;
  };

  // Minimal inline ✓/✗ next to the Test button. The verbose detail
  // ("Authenticated as …") is fired as a toast so the row itself stays
  // compact. ``setResult`` returns nothing — the Toast is side-effectful.
  const setResult = (collector, ok, detail, pending = false) => {
    const node = document.querySelector(`[data-result-for="${collector}"]`);
    if (!node) return;
    if (pending) {
      node.className = "test-result compact pending";
      node.textContent = "…";
      node.title = "Testing…";
      return;
    }
    node.className = `test-result compact ${ok ? "ok" : "err"}`;
    node.textContent = ok ? "✓" : "✕";
    node.title = detail || "";
    const kind = ok ? "ok" : "err";
    const title = ok ? `${collector}: connected` : `${collector}: failed`;
    showToast(detail || (ok ? "OK" : "Failed"), kind, { title });
  };

  const getFieldValue = (path) => {
    const [section, key] = path.split(".");
    return state.config.collectors?.[section]?.[key] ?? "";
  };

  const setFieldValue = (path, value) => {
    const [section, key] = path.split(".");
    state.config.collectors ??= {};
    state.config.collectors[section] ??= {};
    if (key === "projects") {
      state.config.collectors[section][key] = value
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    } else {
      state.config.collectors[section][key] = value;
    }
  };

  const refreshClearButton = (collector) => {
    const btn = document.querySelector(`[data-clear-secret="${collector}"]`);
    if (!btn) return;
    const hasSaved = Boolean(state.secretsPresent[collector]);
    btn.hidden = !hasSaved;
  };

  // Fallback placeholder for saved tokens when the server couldn't compute a
  // preview (shouldn't happen with a current server, but keeps old clients
  // paired with new servers — and vice versa — rendering something sane).
  const FALLBACK_PREVIEW = "•••••••• (saved — leave blank to keep)";

  // Remember each input's markup-authored placeholder so we can restore it
  // when a token gets cleared. Without this we'd lose the "paste token" /
  // "glpat-…" hints after the user clicks Clear.
  const _originalPlaceholders = new WeakMap();

  const updateSecretPlaceholder = (input) => {
    const collector = input.dataset.secret;
    if (!_originalPlaceholders.has(input)) {
      _originalPlaceholders.set(input, input.placeholder || "");
    }
    if (state.pendingClears.has(collector)) {
      input.placeholder = "Will clear on save — paste new token or save to remove";
      return;
    }
    if (state.secretsPresent[collector]) {
      const preview = state.secretsPreview[collector];
      input.placeholder = preview
        ? `${preview} (saved — leave blank to keep)`
        : FALLBACK_PREVIEW;
      return;
    }
    input.placeholder = _originalPlaceholders.get(input) || "";
  };

  // ----- Multi-path repos_dir helpers -----

  // Read whatever shape the server sent and always present the UI with an
  // array. We never persist an empty array back to disk — ``saveReposDirs``
  // filters blanks — so a user who removes all rows "resets" to unset (same
  // as an empty string in the legacy single-path form). This keeps the boot
  // path robust against a config.yaml that's been hand-edited to any shape.
  const readReposDirs = () => {
    const raw = state.config.repos_dir;
    if (Array.isArray(raw)) return raw.slice();
    if (typeof raw === "string" && raw.trim()) return [raw];
    return [];
  };

  // Flush the DOM back into ``state.config.repos_dir``. Called on every input
  // event and on every add/remove — so save() always sees the current UI
  // state without having to re-scan the DOM.
  const syncReposDirsToState = () => {
    const rows = els("#repos-dirs-list .repos-row input");
    state.config.repos_dir = rows.map((input) => input.value);
  };

  const updateRemoveButtons = () => {
    // Only forbid removing the last row when it's non-empty. The user should
    // always be able to clear everything (empty UI ⇒ empty config), so an
    // empty last row keeps its remove button active.
    const rows = els("#repos-dirs-list .repos-row");
    const hasMeaningfulContent = rows.some(
      (row) => row.querySelector("input").value.trim() !== "",
    );
    rows.forEach((row, idx) => {
      const btn = row.querySelector(".btn-remove");
      if (rows.length === 1 && !hasMeaningfulContent) {
        btn.disabled = true;
      } else {
        btn.disabled = false;
      }
      // Aria label tells screen readers which row the button belongs to.
      btn.setAttribute("aria-label", `Remove path ${idx + 1}`);
    });
  };

  // Ask the server to pop a native folder picker. Returns the selected
  // absolute path, or null if the user cancelled or the picker is
  // unavailable on this platform (the caller falls back to typing).
  const browseFolder = async (title) => {
    try {
      const data = await api("POST", "/api/browse-folder", { title });
      if (!data || data.ok === false) {
        if (data && data.error) showToast(data.error, "warn", { title: "Folder picker" });
        return null;
      }
      if (data.cancelled) return null;
      return data.path || null;
    } catch (exc) {
      showToast("Folder picker failed: " + (exc.message || exc), "err", {
        title: "Folder picker",
      });
      return null;
    }
  };

  const addReposRow = (value = "", { focus = false } = {}) => {
    const list = el("#repos-dirs-list");
    const row = document.createElement("div");
    row.className = "repos-row";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "~/Code";
    input.value = value;
    input.setAttribute("aria-label", "Repository parent directory");
    input.addEventListener("input", () => {
      syncReposDirsToState();
      updateRemoveButtons();
    });

    const browse = document.createElement("button");
    browse.type = "button";
    browse.className = "btn btn-ghost btn-inline btn-browse";
    browse.textContent = "Browse…";
    browse.setAttribute("aria-label", "Browse for repository parent directory");
    browse.hidden = !state.folderPickerAvailable;
    browse.addEventListener("click", async () => {
      const picked = await browseFolder("Select a repository parent directory");
      if (picked) {
        input.value = picked;
        syncReposDirsToState();
        updateRemoveButtons();
      }
    });

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-remove";
    btn.textContent = "\u00d7";  // multiplication sign, semantic "remove"
    btn.addEventListener("click", () => {
      const rows = els("#repos-dirs-list .repos-row");
      if (rows.length === 1) {
        // Last row — clear in place rather than leaving the user with zero
        // inputs (confusing) or re-rendering from scratch (jittery).
        input.value = "";
        syncReposDirsToState();
        updateRemoveButtons();
        input.focus();
        return;
      }
      row.remove();
      syncReposDirsToState();
      updateRemoveButtons();
    });

    row.appendChild(input);
    row.appendChild(browse);
    row.appendChild(btn);
    list.appendChild(row);
    if (focus) input.focus();
  };

  const bindReposDirs = () => {
    const list = el("#repos-dirs-list");
    list.innerHTML = "";
    const values = readReposDirs();
    if (values.length === 0) {
      addReposRow("");
    } else {
      values.forEach((v) => addReposRow(v));
    }
    syncReposDirsToState();
    updateRemoveButtons();
    el("#repos-dirs-add").addEventListener("click", () => {
      addReposRow("", { focus: true });
      syncReposDirsToState();
      updateRemoveButtons();
    });
  };

  // ----- Binding -----

  const bindFields = () => {
    els("[data-field]").forEach((input) => {
      const path = input.dataset.field;
      const initial = getFieldValue(path);
      input.value = Array.isArray(initial) ? initial.join(", ") : initial ?? "";
      input.addEventListener("input", () => setFieldValue(path, input.value));
    });

    els("[data-enable]").forEach((toggle) => {
      const collector = toggle.dataset.enable;
      state.config.collectors ??= {};
      state.config.collectors[collector] ??= {};
      toggle.checked = Boolean(state.config.collectors[collector].enabled);
      toggle.addEventListener("change", () => {
        state.config.collectors[collector].enabled = toggle.checked;
        const card = toggle.closest(".card");
        if (card) card.classList.toggle("disabled", !toggle.checked);
      });
      const card = toggle.closest(".card");
      if (card) card.classList.toggle("disabled", !toggle.checked);
    });

    els("[data-secret]").forEach((input) => {
      const collector = input.dataset.secret;
      updateSecretPlaceholder(input);
      refreshClearButton(collector);
      input.addEventListener("input", () => {
        if (input.value) {
          state.dirtySecrets[collector] = input.value;
          // Typing a new token overrides any pending clear.
          state.pendingClears.delete(collector);
        } else {
          delete state.dirtySecrets[collector];
        }
      });
    });

    els("[data-clear-secret]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const collector = btn.dataset.clearSecret;
        state.pendingClears.add(collector);
        delete state.dirtySecrets[collector];
        const input = document.querySelector(`[data-secret="${collector}"]`);
        if (input) {
          input.value = "";
          updateSecretPlaceholder(input);
        }
        showToast(
          `Saved ${collector} token will be removed from keychain and config on next save.`,
          "warn",
          { title: "Token marked for removal" },
        );
      });
    });

    els("[data-test]").forEach((btn) => {
      btn.addEventListener("click", () => runTest(btn.dataset.test));
    });

    const vaultInput = el("#vault_path");
    vaultInput.value = state.config.vault_path ?? "";
    vaultInput.addEventListener("input", (e) => {
      state.config.vault_path = e.target.value;
    });

    const vaultBrowse = el("#vault_path_browse");
    vaultBrowse.hidden = !state.folderPickerAvailable;
    vaultBrowse.addEventListener("click", async () => {
      const picked = await browseFolder("Select your Obsidian vault folder");
      if (picked) {
        vaultInput.value = picked;
        state.config.vault_path = picked;
      }
    });

    bindReposDirs();

    const schedule = state.config.schedule ?? {};
    if (schedule.morning) el("#schedule_morning").value = schedule.morning;
    if (schedule.evening) el("#schedule_evening").value = schedule.evening;
    el("#schedule_weekdays").checked = schedule.weekdays_only !== false;

    ["#schedule_morning", "#schedule_evening"].forEach((sel) => {
      el(sel).addEventListener("input", (e) => {
        state.config.schedule ??= {};
        state.config.schedule[sel === "#schedule_morning" ? "morning" : "evening"] =
          e.target.value;
      });
    });
    el("#schedule_weekdays").addEventListener("change", (e) => {
      state.config.schedule ??= {};
      state.config.schedule.weekdays_only = e.target.checked;
    });

    el("#install-schedule").addEventListener("click", () => callSchedule("install"));
    el("#remove-schedule").addEventListener("click", () => callSchedule("remove"));

    // "Run now" — date picker defaults to today in the user's local
    // timezone. We deliberately read the local date, not UTC, because the
    // note filename the engine writes uses the user's local calendar.
    const today = new Date();
    const localIso =
      today.getFullYear() +
      "-" +
      String(today.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(today.getDate()).padStart(2, "0");
    el("#run-date").value = localIso;
    el("#run-morning").addEventListener("click", () => runFlow("morning"));
    el("#run-evening").addEventListener("click", () => runFlow("evening"));

    el("#save-btn").addEventListener("click", save);
    el("#done-btn").addEventListener("click", shutdown);
  };

  // ----- Actions -----

  // Build a request payload the server can use to test with the user's
  // in-flight form state — essential for first-run, before anything has been
  // saved to disk. ``repos_dir`` goes as an array even for a single path so
  // the server never has to branch on the shape — the save endpoint does the
  // same for the same reason.
  const buildInFlightPayload = () => {
    const reposDirs = (state.config.repos_dir || [])
      .filter((entry) => typeof entry === "string" && entry.trim());
    return {
      repos_dir: reposDirs,
      collectors: state.config.collectors || {},
      secrets: { ...state.dirtySecrets },
    };
  };

  const runTest = async (collector) => {
    setResult(collector, false, "Testing…", true);
    try {
      const data = await api("POST", `/api/test/${collector}`, buildInFlightPayload());
      setResult(collector, data.ok, data.detail || (data.ok ? "OK" : "Failed"));
    } catch (exc) {
      setResult(collector, false, exc.message || "Request failed");
    }
  };

  const callSchedule = async (action) => {
    const node = el("#schedule-result");
    node.className = "test-result pending";
    node.textContent = action === "install" ? "Installing…" : "Removing…";
    const toastTitle = action === "install" ? "Schedule installed" : "Schedule removed";
    try {
      const data = await api("POST", "/api/schedule", { action });
      node.className = `test-result ${data.ok ? "ok" : "err"}`;
      node.textContent = data.message || (data.ok ? "Done" : "Failed");
      showToast(data.message || (data.ok ? "Done" : "Failed"), data.ok ? "ok" : "err", {
        title: data.ok ? toastTitle : "Schedule failed",
      });
    } catch (exc) {
      const msg = exc.message || "Request failed";
      node.className = "test-result err";
      node.textContent = msg;
      showToast(msg, "err", { title: "Schedule failed" });
    }
  };

  // Trigger a manual morning/evening run for the picked date. Both buttons
  // are disabled for the duration so a double-click can't fire two runs
  // (the server would return 409 anyway but disabling is a clearer UX).
  const runFlow = async (mode) => {
    const date = el("#run-date").value;
    const node = el("#run-result");
    const buttons = [el("#run-morning"), el("#run-evening")];
    if (!date) {
      node.className = "test-result err";
      node.textContent = "Pick a date first.";
      showToast("Pick a date first.", "warn", { title: "Run" });
      return;
    }
    buttons.forEach((b) => (b.disabled = true));
    node.className = "test-result pending";
    // Intentionally vague on duration — a no-collector run finishes in
    // milliseconds, a full run with every collector enabled can take
    // 30–60 s. The final toast reports the real duration either way.
    node.textContent = `Running ${mode} for ${date}…`;
    const dismissRunning = showToast(`Running ${mode} for ${date}…`, "info", {
      duration: 0,
      title: "Run in progress",
    });
    try {
      const data = await api("POST", "/api/run", { mode, date });
      dismissRunning?.();
      if (data.ok) {
        const secs = (data.duration_ms / 1000).toFixed(1);
        const msg = `Wrote ${data.note_name} in ${secs}s`;
        node.className = "test-result ok";
        node.textContent = msg;
        showToast(msg, "ok", { title: `${mode} run complete` });
      } else {
        const msg = data.error || "Run failed";
        node.className = "test-result err";
        node.textContent = msg;
        showToast(msg, "err", { title: `${mode} run failed` });
      }
    } catch (exc) {
      dismissRunning?.();
      const msg = exc.message || "Request failed";
      node.className = "test-result err";
      node.textContent = msg;
      showToast(msg, "err", { title: `${mode} run failed` });
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  };

  // Translate the server's per-collector backend map into a single toast
  // message. The old code showed a binary "all keychain / all yaml" which
  // hid mixed-state saves where the keychain rejected one token — users
  // deserve to know if a token is sitting in plaintext.
  const describeSaveOutcome = (data) => {
    const backend = data.secrets_backend || {};
    const writeErrors = data.write_errors || [];
    const changed = Object.keys(backend);

    if (writeErrors.length > 0) {
      return {
        kind: "err",
        text:
          `Saved, but the keychain rejected: ${writeErrors.join(", ")}. ` +
          `Those tokens are now in config.yaml (chmod 600). Fix your keychain ` +
          `and re-save to move them.`,
      };
    }

    if (changed.length === 0) {
      return { kind: "ok", text: "Saved." };
    }

    const inKeyring = changed.filter((c) => backend[c] === "keyring");
    const inYaml = changed.filter((c) => backend[c] === "yaml");
    const cleared = changed.filter((c) => backend[c] === "cleared");

    const parts = [];
    if (inKeyring.length) parts.push(`${inKeyring.join(", ")} → OS keychain`);
    if (inYaml.length) parts.push(`${inYaml.join(", ")} → config.yaml`);
    if (cleared.length) parts.push(`${cleared.join(", ")} cleared`);

    if (inYaml.length && state.keyringAvailable) {
      return {
        kind: "warn",
        text: `Saved. ${parts.join(" · ")}. Keychain was available but not used — check server log.`,
      };
    }
    if (inYaml.length && !state.keyringAvailable) {
      return {
        kind: "warn",
        text: `Saved. ${parts.join(" · ")}. No keychain available — consider installing one.`,
      };
    }
    return { kind: "ok", text: `Saved. ${parts.join(" · ")}.` };
  };

  const save = async () => {
    // A sticky "Saving…" toast covers the whole round-trip; we dismiss
    // it before showing the outcome so users see exactly one toast per
    // save even on a fast loopback.
    const dismissSaving = showToast("Saving…", "info", { duration: 0 });
    try {
      // Pending clears go in as empty strings, which the server interprets
      // as "delete the stored secret".
      const secretsPayload = { ...state.dirtySecrets };
      for (const collector of state.pendingClears) {
        secretsPayload[collector] = "";
      }
      // Send ``repos_dir`` as an array even if the user has only a single
      // path — the server accepts both shapes but normalising here means the
      // in-memory model and the disk model agree.
      const configToSend = {
        ...state.config,
        repos_dir: (state.config.repos_dir || [])
          .filter((entry) => typeof entry === "string" && entry.trim()),
      };
      const data = await api("POST", "/api/config", {
        config: configToSend,
        secrets: secretsPayload,
      });
      state.dirtySecrets = {};
      state.pendingClears.clear();
      state.secretsPresent = data.secrets_present ?? state.secretsPresent;
      state.secretsPreview = data.secrets_preview ?? state.secretsPreview;
      els("[data-secret]").forEach((input) => {
        input.value = "";
        updateSecretPlaceholder(input);
      });
      Object.keys(SECRET_FIELDS).forEach(refreshClearButton);

      dismissSaving?.();
      const outcome = describeSaveOutcome(data);
      showToast(outcome.text, outcome.kind, { title: "Configuration saved" });
    } catch (exc) {
      dismissSaving?.();
      showToast("Save failed: " + (exc.message || exc), "err", { title: "Save failed" });
    }
  };

  const shutdown = async () => {
    try {
      await api("POST", "/api/shutdown");
    } catch {
      /* server already gone */
    }
    document.body.innerHTML =
      '<main style="padding:3rem 1rem;text-align:center;">' +
      '<h1 style="font:600 1.1rem -apple-system,sans-serif;">devjournal setup stopped.</h1>' +
      '<p style="color:#888;">You can close this tab.</p></main>';
  };

  // ----- Boot -----

  const boot = async () => {
    initTheme();
    try {
      const data = await api("GET", "/api/config");
      state.config = data.config || {};
      state.secretsPresent = data.secrets_present || {};
      state.secretsPreview = data.secrets_preview || {};
      state.keyringAvailable = Boolean(data.keyring_available);
      state.folderPickerAvailable = Boolean(data.folder_picker_available);
      state.version = data.version || "";
      setText("#version", state.version ? `v${state.version}` : "");
      bindFields();
      // Announce keychain state *after* bindFields so the toast region
      // has been painted — otherwise the toast slides in against an
      // empty page, which looks like a mistake.
      if (!state.keyringAvailable) {
        showToast(
          "Tokens will be stored in config.yaml (chmod 600).",
          "warn",
          { title: "No OS keychain available", duration: 0 },
        );
      }
    } catch (exc) {
      showToast("Failed to load config: " + (exc.message || exc), "err", {
        title: "Load failed",
        duration: 0,
      });
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
