"""Tests for the Jira collector."""

from __future__ import annotations

from datetime import date

import responses

from devjournal.collectors.jira import JiraCollector
from tests.conftest import scoped_config


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
    cfg = scoped_config(sample_config, "jira")
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
    cfg = scoped_config(sample_config, "jira")
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
    cfg = scoped_config(sample_config, "jira")
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.items == []


def test_collect_skips_when_not_configured():
    collector = JiraCollector()
    result = collector.collect(date(2026, 4, 15), {})
    assert result.items == []


def test_safe_project_list_rejects_invalid_keys():
    collector = JiraCollector()
    cfg = {"projects": ["CAR", "KTON", "'; DROP TABLE --", "lower", "OK123"]}
    valid = collector._safe_project_list(cfg)
    assert valid == "CAR,KTON,OK123"


def test_safe_project_list_empty():
    collector = JiraCollector()
    assert collector._safe_project_list({}) == ""


def test_collect_empty_projects_returns_early():
    """No valid projects should return empty result without making an API call."""
    collector = JiraCollector()
    cfg = {"domain": "x.atlassian.net", "email": "a@b.com", "api_token": "t", "projects": []}
    result = collector.collect(date(2026, 4, 15), cfg)
    assert result.items == []
    assert result.section_id == "jira_activity"


def test_collect_agenda_empty_projects_returns_early():
    collector = JiraCollector()
    cfg = {"domain": "x.atlassian.net", "email": "a@b.com", "api_token": "t", "projects": []}
    result = collector.collect_agenda(date(2026, 4, 15), cfg)
    assert result.items == []
    assert result.section_id == "jira_active"
