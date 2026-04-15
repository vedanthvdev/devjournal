"""Local git collector — scans local repositories for commits by the user today."""

from __future__ import annotations

import logging
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

from devjournal.collector import Collector, CollectorResult

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
        repos_dir = Path(config.get("repos_dir", "")).expanduser()
        author_email = config.get("author_email", "")
        if not repos_dir.is_dir():
            log.warning("Repos directory not found: %s", repos_dir)
            return {}
        if not author_email:
            log.warning("local_git.author_email not set — skipping")
            return {}

        date_str = target_date.isoformat()
        result: dict[str, list[str]] = defaultdict(list)

        for entry in repos_dir.iterdir():
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
                if proc.returncode == 0 and proc.stdout.strip():
                    for line in proc.stdout.strip().splitlines():
                        parts = line.split(" ", 1)
                        msg = parts[1] if len(parts) > 1 else parts[0]
                        result[entry.name].append(msg)
            except (subprocess.TimeoutExpired, Exception):
                continue

        return dict(result)
