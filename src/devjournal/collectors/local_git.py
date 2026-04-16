# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Local git collector — scans local repositories for commits by the user today."""

from __future__ import annotations

import logging
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

from devjournal.collector import Collector, CollectorResult
from devjournal.config import get_repos_dirs

log = logging.getLogger("devjournal")


class LocalGitCollector(Collector):
    name = "local_git"
    config_key = "local_git"

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        repo_commits = self._scan_repos(target_date, config)
        items: list[dict] = []
        for repo, commits in sorted(repo_commits.items()):
            for msg in commits:
                items.append({
                    "type": "commit",
                    "project": repo,
                    "message": msg,
                })
        return CollectorResult(
            section_id="code_changes",
            heading="### Code Changes",
            items=items,
            empty_message="No code changes detected today.",
        )

    @staticmethod
    def _scan_repos(target_date: date, config: dict) -> dict[str, list[str]]:
        # ``get_repos_dirs`` hides whether the user configured a single path
        # (legacy) or a list (post-setup-UI) — the collector is the same either
        # way: scan every configured root one level deep.
        raw_dirs = get_repos_dirs(config)
        author_email = config.get("author_email", "")
        if not raw_dirs:
            log.info("local_git.repos_dir not configured — skipping")
            return {}
        if not author_email:
            log.warning("local_git.author_email not set — skipping")
            return {}

        date_str = target_date.isoformat()
        # Collect per (root, repo_name) up front so we know every commit's
        # origin. We decide the display label *after* scanning, because whether
        # two roots share a repo name only becomes clear at the end. A naive
        # defaultdict keyed on the bare name would silently merge commits from
        # ``~/Code/foo`` and ``~/work/foo`` into a single bullet list, which
        # would be both wrong and hard to debug.
        by_root_name: dict[tuple[str, str], list[str]] = defaultdict(list)

        for raw_dir in raw_dirs:
            repos_dir = Path(raw_dir).expanduser()
            if not repos_dir.is_dir():
                log.warning("Repos directory not found: %s", repos_dir)
                continue
            try:
                entries = sorted(repos_dir.iterdir())
            except OSError as exc:
                log.warning("Could not list %s: %s", repos_dir, exc)
                continue
            root_key = str(repos_dir)
            for entry in entries:
                if not (entry / ".git").exists():
                    continue
                try:
                    proc = subprocess.run(
                        [
                            "git", "log",
                            f"--author={author_email}",
                            f"--since={date_str} 00:00:00",
                            f"--until={date_str} 23:59:59",
                            "--oneline", "--all",
                        ],
                        cwd=str(entry),
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                except (subprocess.TimeoutExpired, Exception):
                    continue
                if proc.returncode != 0 or not proc.stdout.strip():
                    continue
                for line in proc.stdout.strip().splitlines():
                    parts = line.split(" ", 1)
                    msg = parts[1] if len(parts) > 1 else parts[0]
                    by_root_name[(root_key, entry.name)].append(msg)

        # Count name occurrences across roots so we can disambiguate collisions
        # without lengthening every single label.
        name_roots: dict[str, set[str]] = defaultdict(set)
        for root, name in by_root_name:
            name_roots[name].add(root)

        result: dict[str, list[str]] = {}
        for (root, name), commits in by_root_name.items():
            label = name if len(name_roots[name]) == 1 else f"{name} ({root})"
            result[label] = commits
        return result
