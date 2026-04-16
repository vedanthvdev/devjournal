"""Shared fixtures for devjournal tests."""

from __future__ import annotations

import pytest

from devjournal.config import get_collector_config

_SAFE_GLOBAL_KEYS = ("vault_path", "repos_dir")


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


def scoped_config(full_config: dict, collector_key: str) -> dict:
    """Mirror the engine's _scoped_config: global safe keys + collector-specific settings."""
    base = {k: full_config[k] for k in _SAFE_GLOBAL_KEYS if k in full_config}
    base.update(get_collector_config(full_config, collector_key))
    return base
