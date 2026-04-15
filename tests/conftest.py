"""Shared fixtures for devjournal tests."""

from __future__ import annotations

import pytest


@pytest.fixture()
def sample_config(tmp_path):
    """A minimal valid config dict pointing at a temp vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repos = tmp_path / "repos"
    repos.mkdir()
    return {
        "vault_path": str(vault),
        "repos_dir": str(repos),
        "collectors": {
            "jira": {
                "enabled": True,
                "domain": "test.atlassian.net",
                "email": "user@test.com",
                "api_token": "test-token",
                "projects": ["PROJ"],
            },
            "confluence": {"enabled": True},
            "gitlab": {
                "enabled": True,
                "url": "https://gitlab.example.com",
                "token": "glpat-test",
                "username": "testuser",
            },
            "github": {
                "enabled": True,
                "token": "ghp_test",
                "username": "testuser",
            },
            "local_git": {
                "enabled": True,
                "author_email": "user@test.com",
            },
            "cursor": {"enabled": True},
        },
        "schedule": {
            "morning": "08:30",
            "evening": "17:00",
            "weekdays_only": True,
        },
    }
