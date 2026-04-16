"""Tests for the GitHub collector."""

from __future__ import annotations

from datetime import date

import responses

from devjournal.collectors.github import GitHubCollector
from tests.conftest import scoped_config


@responses.activate
def test_collect_push_and_pr_events(sample_config):
    responses.get(
        "https://api.github.com/users/testuser/events",
        json=[
            {
                "type": "PushEvent",
                "created_at": "2026-04-15T10:00:00Z",
                "repo": {"name": "testuser/webapp"},
                "payload": {
                    "ref": "refs/heads/main",
                    "commits": [
                        {"message": "fix: handle null pointer"},
                        {"message": "test: add unit test"},
                    ],
                },
            },
            {
                "type": "PullRequestEvent",
                "created_at": "2026-04-15T14:00:00Z",
                "repo": {"name": "testuser/webapp"},
                "payload": {
                    "action": "opened",
                    "pull_request": {"title": "Add pagination support"},
                },
            },
        ],
    )

    collector = GitHubCollector()
    cfg = scoped_config(sample_config, "github")
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.section_id == "code_changes"
    assert len(result.items) == 3

    pushes = [i for i in result.items if i["type"] == "push"]
    assert len(pushes) == 2
    assert pushes[0]["project"] == "webapp"

    prs = [i for i in result.items if i["type"] == "pr"]
    assert len(prs) == 1
    assert prs[0]["title"] == "Add pagination support"


@responses.activate
def test_collect_filters_by_date(sample_config):
    responses.get(
        "https://api.github.com/users/testuser/events",
        json=[
            {
                "type": "PushEvent",
                "created_at": "2026-04-14T10:00:00Z",
                "repo": {"name": "testuser/old"},
                "payload": {"ref": "refs/heads/main", "commits": [{"message": "old"}]},
            },
        ],
    )
    collector = GitHubCollector()
    cfg = scoped_config(sample_config, "github")
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.items == []


def test_collect_skips_when_not_configured():
    collector = GitHubCollector()
    result = collector.collect(date(2026, 4, 15), {})
    assert result.items == []
