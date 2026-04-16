# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Stacking toast notifications in the setup UI** — replaced the always-on status banner with a lightweight toast system (slide-in top-right, auto-dismiss, click-to-close, four kinds: `ok`/`err`/`warn`/`info`). "Test" button feedback is now a per-collector ✓/✗ glyph paired with a transient toast, so the full "Authenticated as …" message shows briefly then clears instead of squatting permanently next to the button. Save / Run / Schedule flows also pipe through toasts, with sticky "Saving…" / "Running …" toasts replaced by their outcome when the round-trip completes. Respects `prefers-reduced-motion`. No new runtime dependencies — pure vanilla JS + CSS animations.
- **Native folder picker** — new `POST /api/browse-folder` endpoint plus `Browse…` buttons next to the vault path and each local-repos row in the setup UI. The server spawns the OS's native "choose folder" dialog (`osascript` on macOS, `zenity`/`kdialog` on Linux) so users can pick folders graphically instead of hand-typing absolute paths. The endpoint is CSRF-gated like every other mutating endpoint, the picker callable is injectable for tests, and `GET /api/config` now returns a `folder_picker_available` flag so the UI hides the buttons on hosts where no native picker exists.
- **Masked token previews in the setup UI** — the saved-token placeholder now shows the last 4 characters of the stored token behind 8 bullets (e.g. `••••••••wXyZ`), so a user reopening the UI in a new tab can confirm at a glance that their Jira / GitLab / GitHub / Confluence token is still stored. The plaintext token itself never leaves the server: the server reads the keychain, computes the masked preview, and returns only the preview string as a new `secrets_preview` field on both `GET /api/config` and the save response.
- **Multi-path `repos_dir`** — `repos_dir` now accepts a list of paths in addition to the legacy single-string form, so users who keep code in more than one parent directory (e.g. `~/Code` for personal, `~/work` for employer) can point `local_git` at all of them at once. The setup UI renders the list as stacked rows with `+ Add path` / `×` controls; blank rows are dropped at save time. Repo-name collisions across roots (two `foo` directories under different parents) are disambiguated in the evening note so commits never silently merge.
- `devjournal.config.get_repos_dirs(config)` helper normalises the polymorphic `repos_dir` value to a list — called by the `local_git` collector, the `/api/test/local_git` probe, and the setup server, so callers never have to branch on shape.
- **Setup UI** — new `devjournal setup` subcommand launches a local, browser-based wizard for configuring integrations and scheduling. Auto-opens on first run when no config exists.
  - Stdlib-only HTTP server bound to `127.0.0.1` on a random port with per-session CSRF token, `Origin` / `Referer` checks, strict Content-Security-Policy, and 30-minute idle auto-shutdown.
  - "Test connection" buttons for Jira, Confluence, GitLab, GitHub, Local Git, and Cursor — each hits a lightweight identity endpoint and returns a safe, human-readable result (no raw HTTP bodies).
  - "Install / reinstall schedule" button wraps the existing launchd / cron installer.
  - "Run now" card with a date picker (defaulting to today) and morning/evening buttons so users can backfill a note or verify their setup without leaving the wizard; runs are serialized behind a dedicated `run_lock` so a double-click gets `409 Conflict` instead of racing two writers on the same note file.
  - Light / dark theme honouring `prefers-color-scheme` with a manual override persisted in `localStorage`.
  - Disabled "Coming soon" placeholders for Microsoft Teams, Slack, Zoom, and Outlook.
- **OS keychain secret storage** — tokens entered in the setup UI are stored in the macOS Keychain, freedesktop Secret Service, or Windows Credential Locker via the `keyring` library; `config.yaml` falls back to plaintext only when no backend is available. `load_config` transparently reads the keychain so existing YAML-based configs keep working.
- "Clear saved token" affordance — per-secret button in the UI that deletes the token from both the keychain and `config.yaml` on the next save.
- Save responses include a per-collector `secrets_backend` map (`"keyring"` / `"yaml"` / `"cleared"`) and a `write_errors` list so the UI can warn when the keychain rejects a write and the token falls back to plaintext instead of silently downgrading.
- New optional install extra: `pip install devjournal[setup]` pulls in `keyring>=24`.
- Planning doc `docs/plans/setup-ui.md` describing the architecture, security properties, and rollout.
- `SECURITY.md` with vulnerability reporting policy and scope
- `CODE_OF_CONDUCT.md` based on Contributor Covenant v2.1
- `CHANGELOG.md` in Keep a Changelog format
- GitHub issue templates (bug report, feature request) and PR template
- `.github/dependabot.yml` for weekly dependency updates (minor/patch grouped)
- `.github/CODEOWNERS` for default PR reviewer assignment
- SPDX license identifiers (`SPDX-FileCopyrightText`, `SPDX-License-Identifier: MIT`) on all Python source files
- Token-redaction regression tests — one case per `_TOKEN_PATTERN` branch plus false-positive guards for `sk-learn`, lowercase `akia…`, and `Bearer` in prose

### Changed
- Renamed default branch from `main` to `master`
- Updated workflow triggers to reference `master`
- Dropped deprecated `License ::` classifier in favour of PEP 639 SPDX license expression
- `Engine.run_morning` and `Engine.run_evening` now return the `Path` of the note they wrote so callers (CLI and the setup UI's "Run now" button) can surface the file name in their completion message
- Setup UI's `/api/run` now wraps the `Engine()` constructor and the deferred `load_config` / `Engine` imports in the same error-handling try block as the run itself, so a future eager-auth collector that raises in `__init__` (or any `ImportError` in `devjournal.engine`) surfaces as a clean `ok: false` JSON response rather than a torn socket
- Setup UI's "Run now" progress text is now a neutral "Running `<mode>` for `<date>`…" instead of a hard-coded "this can take 30–60 s" — the actual duration is reported in the result banner, and no-collector runs that finish in milliseconds no longer claim they'll take a minute
- `/api/run` now distinguishes "config file is missing" from "config is missing required fields" in its error message, so a user whose config was deleted between save and run gets an accurate prompt instead of being told to fix a vault_path that was actually correct

### Security
- Broadened Cursor-session token redaction to cover GitHub fine-grained PATs (`github_pat_…`), additional `ghX_` prefixes (`ghu_`, `ghs_`, `ghr_`), AWS access keys (`AKIA…`), JWTs (`eyJ…`), and more Slack token types (`xoxa-`, `xoxr-`)
- Tightened `sk-` and `Bearer` patterns to require token-shaped payloads so prose like `sk-learn` or `Bearer token authentication` no longer over-matches
- Pinned `AKIA…` and `eyJ…` to case-sensitive matching via `(?-i:…)` so lowercase prose cannot be silently eaten
- Setup UI's same-origin check now fails closed when both `Origin` and `Referer` are absent on mutating requests (defense-in-depth alongside the CSRF token)
- Setup UI binds loopback-only: `build_server` rejects non-loopback hosts and the `--host` CLI flag was removed so users cannot accidentally expose the wizard on a LAN interface
- Setup UI's config write is now atomic (tempfile + `os.replace`) and the file descriptor is created with mode `0o600`, closing a TOCTOU window where the file briefly existed with umask-default permissions
- Setup UI caps request bodies at 1 MiB and rejects malformed `Content-Length` headers with a 400 instead of a stdlib 500
- Setup UI's JSON body parser now uses a private `_BadRequest` exception instead of string sentinels, closing a (theoretical) collision where a client could send a JSON-encoded string equal to `"__invalid__"` and coax the server into treating a valid payload as a parse failure
- `/api/test/<collector>` now validates that the request body is a JSON object before dereferencing it; previously a non-dict payload (e.g. `[1, 2, 3]`) crashed the handler with `AttributeError` and dropped the connection instead of returning 400
- Atomic config write tolerates platforms where `os.fchmod` is unavailable (Windows on CPython < 3.13) — the call is now guarded and we rely on the post-`os.replace` `path.chmod(0o600)` fallback, plus the raw file descriptor is no longer leaked when `os.fchmod` raises before `os.fdopen` takes ownership
- `build_server` now chmods the parent directory of the caller-supplied `config_path` (or the default path) instead of unconditionally chmodding `~/.config/devjournal`, eliminating a test-suite side-effect on the user's real home directory and ensuring the `0o700` guarantee applies to non-default config locations

### Fixed
- **Setup UI `Test` buttons for Jira / Confluence / GitLab / GitHub no longer clobber the saved token** — every Test click sends the full form state, including the always-empty password field (the UI never echoes saved secrets back). Previously that blank overrode the stored token during merge, causing a cascade where the keychain fallback couldn't find a legacy YAML-only token and probes returned "API token required". Blank secret fields in the overrides are now dropped during merge so the saved value survives, matching what users already expect from "I haven't typed anything new — use what's saved."
- Corrected repository URL slug (`vedanthvasudev` → `vedanthvdev`) in `pyproject.toml`, `README.md`, and `CONTRIBUTING.md`
- Narrowed SECURITY.md's URL-encoding claim to match actual coverage (GitHub usernames in API paths)
- Setup UI's Confluence `Test` button now resolves the Atlassian token correctly when it lives only in the keychain (previously dead code left Confluence thinking no token existed)
- `devjournal setup` test buttons work on first run — the server now accepts the in-flight form state, so users can validate credentials before the first save
- Concurrent saves through the setup UI are serialized via a lock, preventing a torn `config.yaml` on rapid double-clicks
- Dropped the module-global `_state` in the setup server in favour of per-handler class binding so tests (and any future multi-server use) don't race

### Deferred
- "Migrate existing YAML tokens to the keychain" prompt from the plan is tracked separately; YAML-configured tokens keep working today, and users can move them by pasting the value into the UI and saving

## [0.4.2] - 2026-04-16

### Changed
- Switched to git-tag-derived versioning via `hatch-vcs` (no more hardcoded version)
- Release workflow auto-increments patch, creates annotated tag, and publishes GitHub Release
- Non-tagged builds display as `X.Y.Z-alpha`

### Added
- `fallback-version` for builds from non-git source tarballs
- Numeric validation on tag components to prevent silent version corruption
- `--match 'v[0-9]*'` filtering on all `git describe` calls
- Concurrency guard on release job to prevent tag race conditions

## [0.4.1] - 2026-04-16

### Fixed
- Added `encoding="utf-8"` to file opens for Windows robustness
- Schedule time format validation with `_parse_time()` helper
- Carry-forward now preserves task indentation hierarchy
- Version extraction in release workflow uses `tomllib` instead of fragile `grep`

### Changed
- Collector tests use `scoped_config()` helper matching production behaviour

### Added
- CI pipeline: quick-check job, full OS/Python matrix, build verification step

## [0.4.0] - 2026-04-16

### Security
- JQL injection prevention with project key validation
- Scoped collector configs to prevent credential leakage between integrations
- Cursor collector URL-encodes GitHub usernames

### Fixed
- Cursor collector: tighter SQLite query, skip small entries
- Carry-forward searches older notes when most recent has empty section

### Added
- Tests for CLI, scheduler, and scoped config isolation

## [0.3.1] - 2026-04-16

### Fixed
- Single-source version via `importlib.metadata` (no more version drift)
- SQLite connection leak in Cursor collector
- Config file permission check for token safety
- Placeholder regex tightened to avoid matching user content
- Pagination for GitHub and GitLab API calls
- Confluence uses engine's merged config for credentials
- `--date` argument validation with user-friendly error
- `local_git` collector skips when `repos_dir` is missing

### Changed
- Duplicate root-level config and template files removed

### Added
- GitHub Actions CI for tests + lint
- Release workflow with auto-tagging and GitHub Releases

## [0.2.0] - 2026-04-16

### Added
- Initial public release
- Collectors: Jira, Confluence, GitLab, GitHub, local git, Cursor IDE
- Obsidian daily note creation from templates
- Idempotent section updates via HTML comment markers
- Morning agenda and evening summary modes
- OS-level scheduling (macOS launchd, Linux cron)
- YAML configuration with example template
- Cursor hooks and skill for manual triggering

### Fixed
- Collectors sharing `section_id` now merge instead of overwriting
- Cursor session grouping reduces noise from granular sessions
- Project name extraction strips trailing punctuation

[Unreleased]: https://github.com/vedanthvdev/devjournal/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/vedanthvdev/devjournal/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/vedanthvdev/devjournal/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/vedanthvdev/devjournal/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/vedanthvdev/devjournal/compare/v0.2.0...v0.3.1
[0.2.0]: https://github.com/vedanthvdev/devjournal/releases/tag/v0.2.0
