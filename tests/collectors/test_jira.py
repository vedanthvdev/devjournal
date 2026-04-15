"""Tests for the Jira collector."""

from __future__ import annotations

from datetime import date

import responses

from devjournal.collectors.jira import JiraCollector


@responses.activate
def test_collect_returns_activity(sample_config):
    responses.post(
        "https://test.atlassian.net/rest/api/3/search/jql",
        json={
            "issues": [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "summary": "Fix login bug",
                        "status": {"name": "In Progress"},
                        "updated": "2026-04-15T10:00:00.000+0000",
                    },
                }
            ]
        },
    )
    collector = JiraCollector()
    cfg = {**sample_config, **sample_config["collectors"]["jira"]}
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.section_id == "jira_activity"
    assert len(result.items) == 1
    assert result.items[0]["key"] == "PROJ-1"
    assert "Fix login bug" in result.items[0]["summary"]


@responses.activate
def test_collect_agenda_returns_active_tickets(sample_config):
    responses.post(
        "https://test.atlassian.net/rest/api/3/search/jql",
        json={
            "issues": [
                {
                    "key": "PROJ-2",
                    "fields": {
                        "summary": "Add feature X",
                        "status": {"name": "To Do"},
                        "priority": {"name": "High"},
                        "issuetype": {"name": "Story"},
                    },
                }
            ]
        },
    )
    collector = JiraCollector()
    cfg = {**sample_config, **sample_config["collectors"]["jira"]}
    result = collector.collect_agenda(date(2026, 4, 15), cfg)
    assert result.section_id == "jira_active"
    assert len(result.items) == 1


@responses.activate
def test_collect_handles_api_failure(sample_config):
    responses.post(
        "https://test.atlassian.net/rest/api/3/search/jql",
        status=500,
    )
    collector = JiraCollector()
    cfg = {**sample_config, **sample_config["collectors"]["jira"]}
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.items == []


def test_collect_skips_when_not_configured():
    collector = JiraCollector()
    result = collector.collect(date(2026, 4, 15), {})
    assert result.items == []
