"""GitLab collector — push events, merge requests, and comments via the GitLab REST API."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from devjournal.collector import Collector, CollectorResult

log = logging.getLogger("devjournal")


class GitLabCollector(Collector):
    name = "gitlab"
    config_key = "gitlab"

    def __init__(self) -> None:
        self._project_cache: dict[int, str] = {}

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        events = self._fetch_events(target_date, config)
        return CollectorResult(
            section_id="code_changes",
            heading="### Code Changes",
            items=events,
            empty_message="No code changes detected today.",
        )

    def _fetch_events(self, target_date: date, config: dict) -> list[dict]:
        url = config.get("url", "")
        token = config.get("token", "")
        if not url or not token:
            log.info("GitLab not configured — skipping")
            return []

        # GitLab's `after` param is exclusive, so query from the day before.
        prev_date = (target_date - timedelta(days=1)).isoformat()
        target_str = target_date.isoformat()
        headers = {"PRIVATE-TOKEN": token}
        items: list[dict] = []

        try:
            page = 1
            all_events: list[dict] = []
            while page <= 5:
                r = requests.get(
                    f"{url}/api/v4/events",
                    headers=headers,
                    params={"after": prev_date, "per_page": 100, "page": page},
                    timeout=30,
                )
                r.raise_for_status()
                batch = r.json()
                if not batch:
                    break
                all_events.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

            for event in all_events:
                if event.get("created_at", "")[:10] != target_str:
                    continue

                push_data = event.get("push_data", {})
                project_id = event.get("project_id", "")
                project_name = (
                    self._resolve_project(project_id, url, headers) if project_id else ""
                )

                if push_data:
                    commit_count = push_data.get("commit_count", 0)
                    if commit_count == 0:
                        continue
                    items.append({
                        "type": "push",
                        "project": project_name,
                        "message": push_data.get("commit_title", ""),
                        "branch": push_data.get("ref", ""),
                        "commits": commit_count,
                    })
                elif event.get("target_type") == "MergeRequest":
                    items.append({
                        "type": "mr",
                        "project": project_name,
                        "action": event.get("action_name", ""),
                        "title": event.get("target_title", ""),
                    })
                elif event.get("target_type") == "Note":
                    items.append({
                        "type": "comment",
                        "project": project_name,
                        "action": event.get("action_name", ""),
                        "title": event.get("target_title", "comment"),
                    })
        except Exception as e:
            log.warning("GitLab request failed: %s", e)

        return items

    def _resolve_project(self, project_id: int, base_url: str, headers: dict) -> str:
        if project_id in self._project_cache:
            return self._project_cache[project_id]
        try:
            r = requests.get(
                f"{base_url}/api/v4/projects/{project_id}",
                headers=headers,
                params={"simple": True},
                timeout=10,
            )
            if r.status_code == 200:
                name = r.json().get("path", str(project_id))
                self._project_cache[project_id] = name
                return name
        except Exception:
            pass
        self._project_cache[project_id] = str(project_id)
        return str(project_id)
