# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.3] - 2026-04-16

### Changed
- Renamed default branch from `main` to `master`
- Updated all workflow triggers to reference `master`

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

### Fixed
- JQL injection prevention with project key validation
- Scoped collector configs to prevent credential leakage between integrations
- Cursor collector: tighter SQLite query, skip small entries, URL-encode GitHub usernames
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

### Fixed
- Collectors sharing `section_id` now merge instead of overwriting
- Cursor session grouping reduces noise from granular sessions
- Project name extraction strips trailing punctuation

## [0.1.0] - 2026-04-15

### Added
- Initial release
- Collectors: Jira, Confluence, GitLab, GitHub, local git, Cursor IDE
- Obsidian daily note creation from templates
- Idempotent section updates via HTML comment markers
- Morning agenda and evening summary modes
- OS-level scheduling (macOS launchd, Linux cron)
- YAML configuration with example template
- Cursor hooks and skill for manual triggering

[Unreleased]: https://github.com/vedanthvdev/devjournal/compare/v0.4.3...HEAD
[0.4.3]: https://github.com/vedanthvdev/devjournal/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/vedanthvdev/devjournal/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/vedanthvdev/devjournal/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/vedanthvdev/devjournal/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/vedanthvdev/devjournal/compare/v0.2.0...v0.3.1
[0.2.0]: https://github.com/vedanthvdev/devjournal/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/vedanthvdev/devjournal/releases/tag/v0.1.0
