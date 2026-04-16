"""Tests for config loading and validation."""

from __future__ import annotations

import pytest

from devjournal.config import (
    get_collector_config,
    get_repos_dirs,
    is_collector_enabled,
    load_config,
)


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


def _install_fake_keyring(monkeypatch, **seeded):
    """Replace the real SecretStore factory used by config with one wired to
    an in-memory FakeKeyring. Returns the fake so tests can seed more."""
    from devjournal.setup import secrets as secrets_module
    from tests.setup.test_secrets import FakeKeyring

    fake = FakeKeyring()
    for name, value in seeded.items():
        fake.set_password(secrets_module.SERVICE_NAME, name, value)

    real_store = secrets_module.SecretStore

    def factory(*args, **kwargs):
        # Zero-arg constructor is the one config.py uses.
        if not args and not kwargs:
            return real_store(backend=fake)
        return real_store(*args, **kwargs)

    monkeypatch.setattr(secrets_module, "SecretStore", factory)
    return fake


def test_keychain_fills_blank_token_fields(tmp_path, monkeypatch):
    """_resolve_keychain_secrets must populate empty tokens from the keyring."""
    _install_fake_keyring(monkeypatch, jira="keyring-jira", github="keyring-gh")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\n"
        "collectors:\n"
        "  jira:\n"
        "    enabled: true\n"
        "    domain: x.atlassian.net\n"
        "    email: u@e.com\n"
        "    api_token: ''\n"
        "  github:\n"
        "    enabled: true\n"
        "    username: octocat\n"
        "    token: ''\n"
    )
    cfg = load_config(config_file)
    assert cfg["collectors"]["jira"]["api_token"] == "keyring-jira"
    assert cfg["collectors"]["github"]["token"] == "keyring-gh"


def test_keychain_does_not_overwrite_yaml_token(tmp_path, monkeypatch):
    """yaml-populated tokens must win over the keychain for back-compat."""
    _install_fake_keyring(monkeypatch, jira="keyring-jira")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\n"
        "collectors:\n"
        "  jira:\n"
        "    enabled: true\n"
        "    domain: x.atlassian.net\n"
        "    email: u@e.com\n"
        "    api_token: 'yaml-wins'\n"
    )
    cfg = load_config(config_file)
    assert cfg["collectors"]["jira"]["api_token"] == "yaml-wins"


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


# ---------------------------------------------------------------------------
# get_repos_dirs — multi-path normalisation
# ---------------------------------------------------------------------------


def test_get_repos_dirs_legacy_string():
    """A bare string (legacy shape) becomes a one-element list."""
    assert get_repos_dirs({"repos_dir": "/home/me/code"}) == ["/home/me/code"]


def test_get_repos_dirs_list_shape():
    assert get_repos_dirs({"repos_dir": ["/a", "/b"]}) == ["/a", "/b"]


def test_get_repos_dirs_strips_blanks_and_non_strings():
    """Blanks and garbage entries are silently dropped — a mangled config
    must not break the collector. The helper is read-only so we don't
    rewrite the user's config; only the consumer-facing view is cleaned.
    """
    raw = {"repos_dir": ["/a", "", "  ", None, 42, "/b"]}  # type: ignore[list-item]
    assert get_repos_dirs(raw) == ["/a", "/b"]


def test_get_repos_dirs_missing_returns_empty():
    assert get_repos_dirs({}) == []
    assert get_repos_dirs({"repos_dir": None}) == []
    assert get_repos_dirs({"repos_dir": ""}) == []
    assert get_repos_dirs({"repos_dir": []}) == []


def test_load_config_expands_tilde_in_list(tmp_path, monkeypatch):
    """``load_config`` expanded ``~`` for the legacy single-path form; the
    list form must get the same treatment per entry.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\n"
        "repos_dir:\n"
        "  - ~/Code\n"
        "  - ~/work\n"
    )
    cfg = load_config(config_file)
    # Paths are normalised to absolute strings pointing inside ``tmp_path``.
    assert cfg["repos_dir"] == [str(tmp_path / "Code"), str(tmp_path / "work")]
