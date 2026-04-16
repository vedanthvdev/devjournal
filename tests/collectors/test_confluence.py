"""Tests for the Confluence collector."""

from __future__ import annotations

from datetime import date

import responses

from devjournal.collectors.confluence import ConfluenceCollector


def _config(**overrides):
    """Build a flat config that mirrors what scoped_config would produce."""
    base = {
        "domain": "test.atlassian.net",
        "email": "user@test.com",
        "api_token": "token-123",
    }
    base.update(overrides)
    return base


@responses.activate
def test_collect_returns_pages():
    responses.add(
        responses.GET,
        "https://test.atlassian.net/wiki/rest/api/content/search",
        json={
            "results": [
                {
                    "title": "Design Doc",
                    "_links": {"webui": "/spaces/ENG/pages/123/Design+Doc"},
                },
                {
                    "title": "Runbook",
                    "_links": {"self": "https://test.atlassian.net/wiki/rest/api/content/456"},
                },
            ]
        },
        status=200,
    )

    collector = ConfluenceCollector()
    result = collector.collect(date(2026, 4, 15), _config())

    assert result.section_id == "confluence"
    assert len(result.items) == 2
    assert result.items[0]["title"] == "Design Doc"
    assert "test.atlassian.net/wiki" in result.items[0]["link"]
    assert result.items[1]["title"] == "Runbook"


@responses.activate
def test_collect_empty():
    responses.add(
        responses.GET,
        "https://test.atlassian.net/wiki/rest/api/content/search",
        json={"results": []},
        status=200,
    )

    collector = ConfluenceCollector()
    result = collector.collect(date(2026, 4, 15), _config())

    assert result.items == []
    assert result.empty_message


@responses.activate
def test_collect_handles_api_error():
    responses.add(
        responses.GET,
        "https://test.atlassian.net/wiki/rest/api/content/search",
        json={"error": "bad"},
        status=500,
    )

    collector = ConfluenceCollector()
    result = collector.collect(date(2026, 4, 15), _config())

    assert result.items == []


def test_collect_skips_when_unconfigured():
    collector = ConfluenceCollector()
    result = collector.collect(date(2026, 4, 15), {"collectors": {}})

    assert result.items == []
