"""GitHub collector — push events, pull requests, and reviews via the GitHub REST API."""

from __future__ import annotations

import logging
from datetime import date

import requests

from devjournal.collector import Collector, CollectorResult

log = logging.getLogger("devjournal")


class GitHubCollector(Collector):
    name = "github"
    config_key = "github"

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        items = self._fetch_events(target_date, config)
        return CollectorResult(
            section_id="code_changes",
            heading="### Code Changes",
            items=items,
            empty_message="No code changes detected today.",
        )

    def _fetch_events(self, target_date: date, config: dict) -> list[dict]:
        token = config.get("token", "")
        username = config.get("username", "")
        if not token or not username:
            log.info("GitHub not configured — skipping")
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        target_str = target_date.isoformat()
        items: list[dict] = []

        try:
            # Fetch user events (pushes, PRs, reviews, etc.)
            r = requests.get(
                f"https://api.github.com/users/{username}/events",
                headers=headers,
                params={"per_page": 100},
                timeout=30,
            )
            r.raise_for_status()
            for event in r.json():
                event_date = event.get("created_at", "")[:10]
                if event_date != target_str:
                    continue

                repo_name = event.get("repo", {}).get("name", "").split("/")[-1]
                event_type = event.get("type", "")
                payload = event.get("payload", {})

                if event_type == "PushEvent":
                    for commit in payload.get("commits", []):
                        items.append({
                            "type": "push",
                            "project": repo_name,
                            "message": commit.get("message", "").split("\n")[0],
                            "branch": payload.get("ref", "").replace("refs/heads/", ""),
                            "commits": 1,
                        })

                elif event_type == "PullRequestEvent":
                    pr = payload.get("pull_request", {})
                    items.append({
                        "type": "pr",
                        "project": repo_name,
                        "action": payload.get("action", ""),
                        "title": pr.get("title", ""),
                    })

                elif event_type == "PullRequestReviewEvent":
                    pr = payload.get("pull_request", {})
                    items.append({
                        "type": "pr",
                        "project": repo_name,
                        "action": f"reviewed ({payload.get('review', {}).get('state', '')})",
                        "title": pr.get("title", ""),
                    })

                elif event_type in ("IssueCommentEvent", "CommitCommentEvent"):
                    items.append({
                        "type": "comment",
                        "project": repo_name,
                        "action": "commented",
                        "title": payload.get("issue", {}).get("title", "comment"),
                    })

        except Exception as e:
            log.warning("GitHub request failed: %s", e)

        return items
