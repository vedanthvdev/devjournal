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

  const setBanner = (message, kind) => {
    const node = el("#banner");
    node.textContent = message;
    node.className = `banner ${kind}`;
    if (!message) node.classList.add("hidden");
  };

  const setResult = (collector, ok, detail, pending = false) => {
    const node = document.querySelector(`[data-result-for="${collector}"]`);
    if (!node) return;
    if (pending) {
      node.className = "test-result pending";
      node.textContent = detail || "Testing…";
      return;
    }
    node.className = `test-result ${ok ? "ok" : "err"}`;
    node.textContent = (ok ? "✓ " : "✗ ") + detail;
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

  const updateSecretPlaceholder = (input) => {
    const collector = input.dataset.secret;
    if (state.pendingClears.has(collector)) {
      input.placeholder = "Will clear on save — paste new token or save to remove";
    } else if (state.secretsPresent[collector]) {
      input.placeholder = "•••••••• (saved — leave blank to keep)";
    } else {
      // keep the markup-specified placeholder (e.g. "paste token")
    }
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
        setBanner(
          `Saved ${collector} token will be removed from keychain and config on next save.`,
          "warn",
        );
      });
    });

    els("[data-test]").forEach((btn) => {
      btn.addEventListener("click", () => runTest(btn.dataset.test));
    });

    el("#vault_path").value = state.config.vault_path ?? "";
    el("#vault_path").addEventListener("input", (e) => {
      state.config.vault_path = e.target.value;
    });

    el("#repos_dir").value = state.config.repos_dir ?? "";
    el("#repos_dir").addEventListener("input", (e) => {
      state.config.repos_dir = e.target.value;
    });

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
  // saved to disk.
  const buildInFlightPayload = () => ({
    repos_dir: state.config.repos_dir,
    collectors: state.config.collectors || {},
    secrets: { ...state.dirtySecrets },
  });

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
    try {
      const data = await api("POST", "/api/schedule", { action });
      node.className = `test-result ${data.ok ? "ok" : "err"}`;
      node.textContent = data.message || (data.ok ? "Done" : "Failed");
    } catch (exc) {
      node.className = "test-result err";
      node.textContent = exc.message || "Request failed";
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
      return;
    }
    buttons.forEach((b) => (b.disabled = true));
    node.className = "test-result pending";
    // Intentionally vague on duration — a no-collector run finishes in
    // milliseconds, a full run with every collector enabled can take
    // 30–60 s. The final banner reports the real duration so users see
    // the truth either way.
    node.textContent = `Running ${mode} for ${date}…`;
    try {
      const data = await api("POST", "/api/run", { mode, date });
      if (data.ok) {
        const secs = (data.duration_ms / 1000).toFixed(1);
        node.className = "test-result ok";
        node.textContent = `Wrote ${data.note_name} in ${secs}s`;
      } else {
        node.className = "test-result err";
        node.textContent = data.error || "Run failed";
      }
    } catch (exc) {
      node.className = "test-result err";
      node.textContent = exc.message || "Request failed";
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  };

  // Translate the server's per-collector backend map into a single banner
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
    setBanner("Saving…", "ok");
    try {
      // Pending clears go in as empty strings, which the server interprets
      // as "delete the stored secret".
      const secretsPayload = { ...state.dirtySecrets };
      for (const collector of state.pendingClears) {
        secretsPayload[collector] = "";
      }
      const data = await api("POST", "/api/config", {
        config: state.config,
        secrets: secretsPayload,
      });
      state.dirtySecrets = {};
      state.pendingClears.clear();
      state.secretsPresent = data.secrets_present ?? state.secretsPresent;
      els("[data-secret]").forEach((input) => {
        input.value = "";
        updateSecretPlaceholder(input);
      });
      Object.keys(SECRET_FIELDS).forEach(refreshClearButton);

      const outcome = describeSaveOutcome(data);
      setBanner(outcome.text, outcome.kind);
    } catch (exc) {
      setBanner("Save failed: " + (exc.message || exc), "err");
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
      state.keyringAvailable = Boolean(data.keyring_available);
      state.version = data.version || "";
      setText("#version", state.version ? `v${state.version}` : "");
      if (!state.keyringAvailable) {
        setBanner(
          "No OS keychain available — tokens will be stored in config.yaml (chmod 600).",
          "warn",
        );
      }
      bindFields();
    } catch (exc) {
      setBanner("Failed to load config: " + (exc.message || exc), "err");
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
