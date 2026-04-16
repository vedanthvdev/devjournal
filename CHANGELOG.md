# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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

### Security
- Broadened Cursor-session token redaction to cover GitHub fine-grained PATs (`github_pat_…`), additional `ghX_` prefixes (`ghu_`, `ghs_`, `ghr_`), AWS access keys (`AKIA…`), JWTs (`eyJ…`), and more Slack token types (`xoxa-`, `xoxr-`)
- Tightened `sk-` and `Bearer` patterns to require token-shaped payloads so prose like `sk-learn` or `Bearer token authentication` no longer over-matches
- Pinned `AKIA…` and `eyJ…` to case-sensitive matching via `(?-i:…)` so lowercase prose cannot be silently eaten

### Fixed
- Corrected repository URL slug (`vedanthvasudev` → `vedanthvdev`) in `pyproject.toml`, `README.md`, and `CONTRIBUTING.md`
- Narrowed SECURITY.md's URL-encoding claim to match actual coverage (GitHub usernames in API paths)

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
