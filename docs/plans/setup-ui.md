# devjournal setup UI — implementation plan

**Status:** Draft — pending approval to implement
**Owner:** @vedanthvdev
**Target release:** v0.5.0

## 1. Goals

1. First-time users can configure devjournal end-to-end without hand-editing YAML.
2. Existing users can add / reconfigure / disable integrations visually.
3. Each integration exposes a "Where do I get this token?" link and a "Test connection" button so users know the credentials work before saving.
4. Morning / evening times and weekdays-only are editable in the UI, with a button that installs (or reinstalls) the OS schedule.
5. Stays inside the `pip install devjournal` install footprint — **no Node, no Electron, no extra daemons**.
6. Light / dark theme, respecting OS preference with a manual override.

## 2. Non-goals (explicitly out of scope)

- Running or scheduling the actual collectors from the UI (the UI only configures; `devjournal morning` / `evening` still run via CLI + schedule).
- Viewing past daily notes or collector output — Obsidian already does that.
- Multi-user / remote access. The UI binds to `127.0.0.1` only.
- Windows schedule install in the UI (not currently supported by `scheduler.py` either — out of scope here, but the UI should still let Windows users save config).
- Teams / Slack / Zoom actual integrations (cards are placeholders only).

## 3. User journeys

### 3.1 First run
1. User runs `devjournal` (any subcommand) with no config.
2. Existing behavior: CLI errors with "Run `devjournal init`". **New**: instead, prompt "No config found — open setup UI? [Y/n]" and, on yes, launch the UI.
3. Browser opens at `http://127.0.0.1:<port>/`. Form is pre-filled from `config.example.yaml` defaults.
4. User fills what they need, tests each integration, clicks **Save**.
5. After save, a button appears: **Install schedule**. One click writes the launchd plist / crontab entry.
6. User closes the browser tab or clicks **Done**; the local server exits.

### 3.2 Edit existing config
1. User runs `devjournal setup` explicitly.
2. Existing `~/.config/devjournal/config.yaml` is loaded; tokens are pulled from the OS keychain where available and shown as `••••••••` with a "Change" button (never echoed back into the DOM).
3. User toggles collectors on/off, re-runs tests, saves.

### 3.3 Add a new integration later
Same as 3.2 — e.g. enable GitHub, paste token, Test, Save.

## 4. Architecture

```
┌─────────────────────────────────────────────┐
│  Browser  (localhost:<port>, single page)   │
│  - index.html, app.js, styles.css           │
│  - fetch() against local JSON API           │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│  devjournal.setup.server                    │
│  (stdlib http.server + BaseHTTPRequestHandler)│
│  - GET  /                → static index.html │
│  - GET  /static/*        → js/css/assets    │
│  - GET  /api/config      → current config   │
│  - POST /api/config      → save config      │
│  - POST /api/test/<int>  → probe integration│
│  - POST /api/schedule    → install/remove   │
│  - POST /api/shutdown    → exit gracefully  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│  devjournal.setup.secrets   (new)           │
│  - keyring-backed store with yaml fallback  │
│                                             │
│  devjournal.config           (existing)     │
│  devjournal.scheduler        (existing)     │
│  devjournal.collectors.*     (existing —    │
│    reused for connection probes)            │
└─────────────────────────────────────────────┘
```

- **Stdlib only** on the server side. No Flask / FastAPI.
- Everything lives under `src/devjournal/setup/`.

## 5. UI layout (single page)

```
┌───────────────────────────────────────────────────────────┐
│  devjournal setup                        [☀ / ☾]   [Done] │ ← top bar
├───────────────────────────────────────────────────────────┤
│  Vault                                                    │
│  ├ vault_path  [~/Documents/Obsidian Vault          ] [⎇] │
│  └ repos_dir   [~/Code                              ] [⎇] │
├───────────────────────────────────────────────────────────┤
│  Integrations                                             │
│                                                           │
│  ┌──── Atlassian (Jira + Confluence) ─── [●on] ────────┐  │
│  │  Domain   [yourco.atlassian.net]                    │  │
│  │  Email    [you@yourco.com       ]                   │  │
│  │  Token    [•••••••••] [Change]     How to get this→ │  │
│  │  Projects [CAR, KTON            ]                   │  │
│  │  ☑ Also collect Confluence activity                 │  │
│  │                          [Test connection] ✓ ok     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌──── GitLab ──────────────────────── [●on] ──────────┐  │
│  │  URL      [https://gitlab.com   ]                   │  │
│  │  Username [you             ]                        │  │
│  │  Token    [•••••••••] [Change]     How to get this→ │  │
│  │                          [Test connection]          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌──── GitHub ───────────── [○off]  ─────────────────── │  │
│  ┌──── Local Git ────────── [●on]  ──────────────────── │  │
│  ┌──── AI agents ────────── [●on]  ──────────────────── │  │
│  │  Cursor       [detected: ~/Library/Application...]  │  │
│  │  Claude Code  [not detected]                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ── Coming soon ─────────────────────────────────────────  │
│  ┌ Microsoft Teams ┐  ┌ Slack ┐  ┌ Zoom ┐ (disabled)      │
│                                                           │
├───────────────────────────────────────────────────────────┤
│  Schedule                                                 │
│  Morning [ 08:30 ]   Evening [ 17:00 ]  ☑ Weekdays only   │
│                      [Install / Reinstall schedule]       │
├───────────────────────────────────────────────────────────┤
│                                      [ Save ]    [ Done ] │
└───────────────────────────────────────────────────────────┘
```

- One page, no wizard steps.
- **Save** writes config + stores secrets; **Install schedule** is a separate button so users don't silently re-register launchd on every small config edit.
- Collectors with no secrets (Local Git, Cursor) render as collapsed "●on" cards with no token field.

## 6. Backend API (localhost only)

| Method | Path               | Body                                  | Response                                     |
|--------|--------------------|---------------------------------------|----------------------------------------------|
| GET    | `/`                | —                                     | index.html                                   |
| GET    | `/static/<file>`   | —                                     | css / js / svg                               |
| GET    | `/api/config`      | —                                     | `{config: {...}, secrets_present: {jira:true,...}}` — **never returns token values** |
| POST   | `/api/config`      | `{config: {...}, secrets: {jira:"..."}}` — only keys the user changed | `{ok: true}` or validation errors            |
| POST   | `/api/test/<name>` | —                                     | `{ok:true, detail:"Logged in as ..."}` or `{ok:false, error:"..."}` |
| POST   | `/api/schedule`    | `{action: "install"\|"remove"}`       | `{ok:true, message:"..."}`                   |
| POST   | `/api/shutdown`    | —                                     | `204`, then `sys.exit(0)`                    |

### Security properties of the server
- **Bind**: `127.0.0.1` only (never `0.0.0.0`).
- **Port**: OS-assigned random free port (`bind((“127.0.0.1”, 0))`).
- **CSRF**: all mutating endpoints require an `X-DevJournal-Token` header equal to a random token generated at startup and injected into the HTML. Prevents drive-by localhost attacks from other browser tabs.
- **Same-origin**: reject requests where `Origin` / `Referer` is not `http://127.0.0.1:<port>`.
- **Timeout**: server auto-shuts after 30 min of no activity so forgotten sessions don't linger.
- **No CORS**: no cross-origin headers at all.

## 7. Secret storage (`devjournal.setup.secrets`)

- New optional dependency: `keyring>=24`. Added to `[project.optional-dependencies].setup`, pulled in by `pip install devjournal[setup]`, and always attempted from `devjournal setup`.
- If `keyring` is available **and** a working backend exists (macOS Keychain, freedesktop Secret Service, Windows Credential Locker): store each token under service `devjournal`, account `<collector>` (e.g. `jira`, `gitlab`, `github`).
- If `keyring` is unavailable or has no backend (e.g. headless Linux with no Secret Service): fall back to writing the token into `config.yaml` (existing behaviour), chmod 600, and warn the user in the UI with a yellow banner.
- **Config loading (`devjournal.config`) changes**: when a collector section has `api_token: ""` / `token: ""`, try `keyring.get_password("devjournal", collector_name)` and merge. Existing YAML-based configs keep working unchanged (back-compat).
- Document the migration path in `CHANGELOG.md` and `README.md`: on first `devjournal setup` run, if we detect tokens in YAML we offer to move them to the keychain.

## 8. "Test connection" probes

| Collector     | Endpoint                                            | Success criterion                |
|---------------|-----------------------------------------------------|----------------------------------|
| Jira          | `GET {domain}/rest/api/3/myself`                    | 200 + `emailAddress` present     |
| Confluence    | `GET {domain}/wiki/rest/api/user/current`           | 200                              |
| GitLab        | `GET {url}/api/v4/user`                             | 200 + `username` matches config  |
| GitHub        | `GET https://api.github.com/user`                   | 200 + `login` matches config     |
| Local Git     | `git log --author=<email> -n1 -- <repos_dir>`       | exit 0 (at least one commit)     |
| Cursor        | detect `~/Library/Application Support/Cursor/...` / `~/.config/Cursor/...` | path exists |

Each probe is a small function in `devjournal.setup.probes`. Returns `(ok: bool, detail: str)` — never the raw token, never the full HTTP body. 5s timeout per probe.

## 9. Schedule install

- Wraps existing `devjournal.scheduler.install_schedule(config)` / `remove_schedule()`.
- UI surfaces the stdout/stderr as a textarea for transparency (users like knowing what got written).

## 10. Theming

- Single `styles.css` using CSS custom properties: `--bg`, `--fg`, `--surface`, `--accent`, `--border`, `--ok`, `--warn`, `--err`.
- `:root` = light values. `@media (prefers-color-scheme: dark)` overrides.
- Manual toggle sets `data-theme="light"` / `"dark"` on `<html>`; that wins over system preference. Choice persisted in `localStorage["devjournal-theme"]`.
- Two SVG icons (sun / moon) inlined in the HTML — no icon font.

## 11. "Coming soon" placeholders

Rendered as greyed-out cards with a small `Coming soon` pill and an emoji or SVG. Clicking them does nothing (no modal, no inputs) — keeps the form trivial and prevents half-configured integrations.

## 12. File layout (new additions)

```
src/devjournal/
├── setup/
│   ├── __init__.py           # public: run_setup_ui()
│   ├── server.py             # http.server handler + routes
│   ├── secrets.py            # keyring wrapper with yaml fallback
│   ├── probes.py             # test-connection functions
│   ├── schemas.py            # dataclasses for request/response payloads
│   └── assets/
│       ├── index.html
│       ├── app.js
│       ├── styles.css
│       └── logo.svg
├── cli.py                    # + new subcommand: `devjournal setup`
└── config.py                 # + secret-resolution hook
```

Packaging: add `"devjournal.setup.assets"` to `[tool.hatch.build]` `include` (and verify via `pip install .` + `importlib.resources.files(...)`).

## 13. CLI changes

- New subcommand: `devjournal setup` (`_cmd_setup` in `cli.py`).
  - `--no-browser`: skip `webbrowser.open`; just print the URL.
  - `--host 127.0.0.1` / `--port 0`: escape hatches for debugging.
- `_cmd_run` (and `_cmd_schedule`) in `cli.py`: when `load_config` would `sys.exit(1)` because the file is missing, detect that from `main()` and offer to launch the UI (interactive TTY only; honour `--no-ui` env).

## 14. Dependencies added

- `keyring>=24` (runtime, **optional** via `[setup]` extra).
- No new test deps — `pytest` + `responses` (already present) cover probes; the HTTP handler gets its own tests with stdlib `http.client`.

## 15. Testing strategy

- **Unit**
  - `secrets.py`: store/load/delete round trip with an in-memory backend (fakekeyring).
  - `probes.py`: one test per collector, HTTP mocked via `responses`.
  - `server.py`: small tests for CSRF header enforcement, origin enforcement, 404 for unknown routes, shutdown endpoint.
- **Integration**
  - Start the server in a thread, hit `/api/config`, `/api/config` (POST), `/api/test/jira`, `/api/schedule` (remove), `/api/shutdown`. Assert config file contents and keyring state at each step.
- **Manual acceptance checklist**
  1. Fresh machine, no config → `devjournal setup` → fill form → save → config.yaml + keychain correct.
  2. Test connection green for each integration with a real token.
  3. Install schedule → `launchctl list | grep devjournal` shows both jobs.
  4. Reopen UI → tokens show as `••••••••`, no plaintext echoed in DOM or network.
  5. Light/dark toggle respects OS default on first load, persists after reload.
  6. Kill browser mid-session → server auto-shuts after 30 min idle timeout.
  7. `pip install devjournal` (without `[setup]` extra) → `devjournal setup` prints a friendly message telling the user to `pip install devjournal[setup]`.

## 16. Security considerations (in addition to §6)

- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:` on the served HTML — prevents any remote fetch if a token accidentally leaks into the DOM.
- The CSRF token is never logged. Server logs redact `X-DevJournal-Token`.
- `keyring` errors fall back quietly but produce a single warning so users aren't surprised tokens are still in YAML.
- After save, the server zeroes out its in-memory copy of any token before returning.

## 17. Documentation updates

- `README.md`: add "Quick start" section that just says `pip install devjournal[setup] && devjournal setup`.
- `CHANGELOG.md` under `[Unreleased]` → `### Added`.
- New page `docs/setup-ui.md` with screenshots (added post-implementation).
- `config.example.yaml`: add a comment line pointing at the UI.

## 18. Rollout plan

1. **PR 1 — scaffolding** (no user-visible change): `src/devjournal/setup/` package, empty modules, `keyring` extra, tests for `secrets.py`. CI green.
2. **PR 2 — server + static UI** (happy path): form renders, save writes YAML, no keychain yet. Tests for server + CSRF.
3. **PR 3 — keychain migration**: `secrets.py` wired up, `config.py` reads from keychain, opt-in migration prompt in the UI.
4. **PR 4 — test connection + schedule install buttons**: probes + schedule endpoint + UI wiring.
5. **PR 5 — first-run auto-launch + polish**: light/dark, empty-state hints, README/CHANGELOG, version bump to `v0.5.0`.

Each PR is independently mergeable and leaves `main` in a working state. We ship v0.5.0 after PR 5.

## 19. Open questions / risks

1. **Branch naming**: repo rule is `ABC-XXXX`; devjournal has no ticket tracker. Proposal: use `ui/<short-slug>` (e.g. `ui/scaffold`, `ui/server`). Needs explicit OK since it breaks the personal convention.
2. **`webbrowser.open` on headless Linux / WSL**: will fail silently. UI always prints the URL as fallback — is that good enough?
3. **Keychain on Linux without Secret Service** (CI, servers, minimal distros): falls back to YAML. Acceptable for v0.5.0?
4. **macOS 14+ Keychain prompt**: first write to the `devjournal` service will prompt the user "allow devjournal to access Keychain" — document this in README so it's not surprising.
5. **Token migration**: if a user already has tokens in YAML, do we automatically move them to keychain on next `setup`, or only on explicit "Migrate" click? Default proposal: **prompt once, never move silently**. _Deferred from the initial setup-UI PR — tracked separately. For now, yaml-configured tokens keep working (config.py reads them as before) and users can move them by pasting the value into the UI and saving._

## 20. Acceptance criteria

- `pip install devjournal[setup]` works on macOS + Linux.
- `devjournal setup` opens a working form; saving writes a valid config that `devjournal evening` can load.
- Every listed integration has a working Test button.
- Schedule install/remove works from the UI on macOS (launchd) and Linux (cron).
- New + existing tests pass; ruff clean; coverage not reduced.
- Light + dark theme both render correctly (manual screenshot check).
