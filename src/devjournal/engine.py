# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Orchestrator that discovers collectors, runs them, and writes results to the note.

The engine is the single coordination point — collectors and formatters
never reference each other directly.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from devjournal.collector import Collector, CollectorResult
from devjournal.collectors import get_all_collector_classes
from devjournal.config import get_collector_config, is_collector_enabled
from devjournal.formatter import format_carry_forward, format_result
from devjournal.note import ensure_daily_note, get_carry_forward, update_section

log = logging.getLogger("devjournal")

_SAFE_GLOBAL_KEYS = ("vault_path", "repos_dir")

_PLACEHOLDER_RE = re.compile(r"^\*No \w[^*]{0,60}\.\*$")


def _section_is_empty(content: str, section_id: str) -> bool:
    """Return True when the section either doesn't exist or only has a heading / placeholder.

    Placeholder lines follow the pattern ``*No <word>...*`` such as
    ``*No activity.*`` or ``*No active tickets found.*``.  This avoids
    false-positives on bold text (``**word**``) or user-written italic prose.
    """
    match = re.search(
        rf"<!-- BEGIN:{re.escape(section_id)} -->(.*?)<!-- END:{re.escape(section_id)} -->",
        content,
        re.DOTALL,
    )
    if not match:
        return True
    body = match.group(1).strip()
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    non_heading = [ln for ln in lines if not ln.startswith("#")]
    if not non_heading:
        return True
    return all(_PLACEHOLDER_RE.match(ln) for ln in non_heading)


class Engine:
    """Discovers enabled collectors and orchestrates a morning or evening run."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._collectors = self._discover_collectors()

    def _scoped_config(self, collector_key: str) -> dict[str, Any]:
        """Build a config dict containing only global safe keys + collector-specific settings."""
        base = {k: self._config[k] for k in _SAFE_GLOBAL_KEYS if k in self._config}
        base.update(get_collector_config(self._config, collector_key))
        return base

    def _discover_collectors(self) -> list[Collector]:
        """Instantiate every collector whose config_key is enabled."""
        enabled: list[Collector] = []
        for cls in get_all_collector_classes():
            if not cls.config_key:
                continue
            if is_collector_enabled(self._config, cls.config_key):
                enabled.append(cls())
                log.debug("Enabled collector: %s", cls.name)
            else:
                log.debug("Skipped collector (disabled): %s", cls.name)
        return enabled

    def run_morning(self, target_date: date) -> Path:
        """Populate the morning agenda: active tickets and carry-forward items.

        Returns the path of the note that was written so callers (the CLI,
        the setup-UI ``Run now`` button, etc.) can report it back to the
        user.
        """
        log.info("Running morning agenda for %s", target_date)
        note_path = ensure_daily_note(self._config["vault_path"], target_date)
        content = note_path.read_text()

        agenda_results = self._collect_agenda(target_date)
        for result in agenda_results:
            content = update_section(content, result.section_id, format_result(result))

        carry_items = get_carry_forward(self._config["vault_path"], target_date)
        content = update_section(
            content, "carry_forward", format_carry_forward(carry_items)
        )

        note_path.write_text(content)
        log.info(
            "Morning agenda updated: %s (%d sections, %d carry-forward)",
            note_path.name,
            len(agenda_results),
            len(carry_items),
        )
        return note_path

    def run_evening(self, target_date: date) -> Path:
        """Populate the work log with the full day's activity.

        Returns the path of the note that was written so callers can
        surface it (e.g. the UI's ``Run now`` banner).
        """
        log.info("Running evening summary for %s", target_date)
        note_path = ensure_daily_note(self._config["vault_path"], target_date)
        content = note_path.read_text()

        results = self._collect_all(target_date)
        for result in results:
            content = update_section(content, result.section_id, format_result(result))

        agenda_results = self._collect_agenda(target_date, existing_content=content)
        for result in agenda_results:
            content = update_section(content, result.section_id, format_result(result))

        carry_items = get_carry_forward(self._config["vault_path"], target_date)
        content = update_section(
            content, "carry_forward", format_carry_forward(carry_items)
        )

        note_path.write_text(content)

        total_items = sum(len(r.items) for r in results)
        log.info(
            "Evening summary updated: %s (%d collectors, %d total items)",
            note_path.name,
            len(results),
            total_items,
        )
        return note_path

    def _collect_all(self, target_date: date) -> list[CollectorResult]:
        """Run every enabled collector's ``collect`` method.

        Multiple collectors may share the same ``section_id`` (e.g. both
        GitLab and local_git produce ``code_changes``). Their items are
        merged into a single result so the note gets one unified section.
        """
        raw: list[CollectorResult] = []
        for collector in self._collectors:
            try:
                cfg = self._scoped_config(collector.config_key)
                result = collector.collect(target_date, cfg)
                raw.append(result)
            except Exception:
                log.warning("Collector '%s' failed", collector.name, exc_info=True)

        merged: dict[str, CollectorResult] = {}
        for result in raw:
            existing = merged.get(result.section_id)
            if existing is not None:
                merged[result.section_id] = CollectorResult(
                    section_id=existing.section_id,
                    heading=existing.heading,
                    items=[*existing.items, *result.items],
                    empty_message=existing.empty_message,
                )
            else:
                merged[result.section_id] = result
        return list(merged.values())

    def _collect_agenda(
        self, target_date: date, existing_content: str | None = None
    ) -> list[CollectorResult]:
        """Run every enabled collector's ``collect_agenda`` method.

        When *existing_content* is provided (evening backfill), collectors whose
        section is already populated are skipped to avoid redundant API calls.
        """
        results: list[CollectorResult] = []
        for collector in self._collectors:
            try:
                cfg = self._scoped_config(collector.config_key)
                result = collector.collect_agenda(target_date, cfg)
                if result is None:
                    continue
                if existing_content and not _section_is_empty(existing_content, result.section_id):
                    continue
                results.append(result)
            except Exception:
                log.warning("Collector '%s' agenda failed", collector.name, exc_info=True)
        return results
