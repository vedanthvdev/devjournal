"""Tests for the GitLab collector."""

from __future__ import annotations

from datetime import date

import responses

from devjournal.collectors.gitlab import GitLabCollector


@responses.activate
def test_collect_push_events(sample_config):
    responses.get(
        "https://gitlab.example.com/api/v4/events",
        json=[
            {
                "created_at": "2026-04-15T10:00:00.000Z",
                "action_name": "pushed to",
                "project_id": 42,
                "push_data": {
                    "commit_count": 2,
                    "ref": "main",
                    "commit_title": "Fix auth flow",
                },
            },
        ],
    )
    responses.get(
        "https://gitlab.example.com/api/v4/projects/42",
        json={"path": "backend-service"},
    )

    collector = GitLabCollector()
    cfg = {**sample_config, **sample_config["collectors"]["gitlab"]}
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.section_id == "code_changes"
    assert len(result.items) == 1
    assert result.items[0]["project"] == "backend-service"
    assert result.items[0]["message"] == "Fix auth flow"


@responses.activate
def test_collect_filters_out_other_dates(sample_config):
    responses.get(
        "https://gitlab.example.com/api/v4/events",
        json=[
            {
                "created_at": "2026-04-14T23:00:00.000Z",
                "action_name": "pushed to",
                "project_id": 1,
                "push_data": {"commit_count": 1, "ref": "main", "commit_title": "old"},
            },
        ],
    )
    collector = GitLabCollector()
    cfg = {**sample_config, **sample_config["collectors"]["gitlab"]}
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.items == []


@responses.activate
def test_collect_skips_zero_commit_pushes(sample_config):
    responses.get(
        "https://gitlab.example.com/api/v4/events",
        json=[
            {
                "created_at": "2026-04-15T10:00:00.000Z",
                "action_name": "pushed to",
                "project_id": 1,
                "push_data": {"commit_count": 0, "ref": "main", "commit_title": ""},
            },
        ],
    )
    collector = GitLabCollector()
    cfg = {**sample_config, **sample_config["collectors"]["gitlab"]}
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.items == []


def test_collect_skips_when_not_configured():
    collector = GitLabCollector()
    result = collector.collect(date(2026, 4, 15), {})
    assert result.items == []
