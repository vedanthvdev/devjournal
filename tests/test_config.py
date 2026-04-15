"""Tests for config loading and validation."""

from __future__ import annotations

import pytest

from devjournal.config import get_collector_config, is_collector_enabled, load_config


def test_load_config_from_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\n"
        "collectors:\n"
        "  jira:\n"
        "    enabled: true\n"
        "    domain: test.atlassian.net\n"
    )
    cfg = load_config(config_file)
    assert cfg["vault_path"] == "/tmp/vault"
    assert cfg["collectors"]["jira"]["enabled"] is True


def test_load_config_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_config_missing_vault_path(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("collectors: {}\n")
    with pytest.raises(SystemExit):
        load_config(config_file)


def test_get_collector_config(sample_config):
    jira_cfg = get_collector_config(sample_config, "jira")
    assert jira_cfg["domain"] == "test.atlassian.net"


def test_get_collector_config_missing(sample_config):
    assert get_collector_config(sample_config, "nonexistent") == {}


def test_is_collector_enabled(sample_config):
    assert is_collector_enabled(sample_config, "jira") is True


def test_is_collector_disabled(sample_config):
    sample_config["collectors"]["jira"]["enabled"] = False
    assert is_collector_enabled(sample_config, "jira") is False


def test_is_collector_enabled_missing_key(sample_config):
    assert is_collector_enabled(sample_config, "outlook") is False


def test_vault_path_expanded(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("vault_path: ~/my-vault\n")
    cfg = load_config(config_file)
    assert "~" not in cfg["vault_path"]
    assert cfg["vault_path"].endswith("my-vault")


def test_confluence_inherits_jira_credentials():
    config = {
        "collectors": {
            "jira": {
                "enabled": True,
                "domain": "corp.atlassian.net",
                "email": "dev@corp.com",
                "api_token": "jira-tok",
            },
            "confluence": {"enabled": True},
        }
    }
    cfg = get_collector_config(config, "confluence")
    assert cfg["domain"] == "corp.atlassian.net"
    assert cfg["email"] == "dev@corp.com"
    assert cfg["api_token"] == "jira-tok"


def test_confluence_prefers_atlassian_over_jira():
    config = {
        "collectors": {
            "atlassian": {
                "domain": "shared.atlassian.net",
                "email": "shared@corp.com",
                "api_token": "shared-tok",
            },
            "jira": {
                "enabled": True,
                "domain": "jira.atlassian.net",
                "email": "jira@corp.com",
                "api_token": "jira-tok",
            },
            "confluence": {"enabled": True},
        }
    }
    cfg = get_collector_config(config, "confluence")
    assert cfg["domain"] == "shared.atlassian.net"
    assert cfg["api_token"] == "shared-tok"


def test_confluence_own_config_takes_precedence():
    config = {
        "collectors": {
            "jira": {
                "enabled": True,
                "domain": "jira.atlassian.net",
                "email": "jira@corp.com",
                "api_token": "jira-tok",
            },
            "confluence": {
                "enabled": True,
                "domain": "conf.atlassian.net",
                "email": "conf@corp.com",
                "api_token": "conf-tok",
            },
        }
    }
    cfg = get_collector_config(config, "confluence")
    assert cfg["domain"] == "conf.atlassian.net"
    assert cfg["api_token"] == "conf-tok"
