# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Configuration loading and validation.

Reads a YAML file (default ``~/.config/devjournal/config.yaml``) and exposes
the settings as a plain dict. The ``devjournal init`` command creates this
file from the bundled example.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("devjournal")

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "devjournal"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"

REQUIRED_KEYS = ["vault_path"]


def _check_config_permissions(config_path: Path) -> None:
    """Warn if the config file is readable by group or others."""
    try:
        mode = config_path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            log.warning(
                "Config file %s is readable by other users (mode %s). "
                "It contains API tokens — run: chmod 600 %s",
                config_path,
                oct(mode)[-3:],
                config_path,
            )
    except OSError:
        pass


# Collectors whose primary token can be stored in the OS keychain. Map each
# collector to the yaml field that would normally hold the plaintext token —
# when yaml is empty we consult the keychain before giving up.
_KEYCHAIN_SECRET_KEYS: dict[str, str] = {
    "jira": "api_token",
    "gitlab": "token",
    "github": "token",
}


def _resolve_keychain_secrets(config: dict[str, Any]) -> None:
    """Fill empty token fields from the OS keychain, in-place.

    Keeps existing YAML-configured tokens untouched (back-compat) — the
    keychain only fills blanks. Silently no-ops when ``keyring`` is not
    installed so the base package stays dependency-free.
    """
    try:
        from devjournal.setup.secrets import SecretStore
    except Exception:  # pragma: no cover — defensive; setup should always import
        return

    store = SecretStore()
    if not store.keyring_available:
        return

    collectors = config.get("collectors")
    if not isinstance(collectors, dict):
        return

    for name, yaml_key in _KEYCHAIN_SECRET_KEYS.items():
        section = collectors.get(name)
        if not isinstance(section, dict):
            continue
        if section.get(yaml_key):
            continue  # yaml wins when populated
        result = store.read(name, yaml_value=None)
        if result.value:
            section[yaml_key] = result.value


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the YAML configuration file.

    Args:
        path: Explicit path to the config file. Falls back to
              ``~/.config/devjournal/config.yaml``.

    Returns:
        Parsed config dict.

    Raises:
        SystemExit: If the file is missing or required keys are absent.
    """
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        log.error(
            "Config file not found: %s\nRun 'devjournal init' to create one.",
            config_path,
        )
        sys.exit(1)

    if os.name != "nt":
        _check_config_permissions(config_path)

    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f) or {}

    missing = [k for k in REQUIRED_KEYS if not config.get(k)]
    if missing:
        log.error("Missing required config keys: %s", ", ".join(missing))
        sys.exit(1)

    config["vault_path"] = str(Path(config["vault_path"]).expanduser())

    # ``repos_dir`` is polymorphic on disk — historically a single string,
    # now also a list of strings. Normalise paths in place but keep the
    # original shape so re-serialising the config (e.g. from the setup UI)
    # doesn't rewrite single-path users into lists against their will.
    raw_repos = config.get("repos_dir")
    if isinstance(raw_repos, str) and raw_repos:
        config["repos_dir"] = str(Path(raw_repos).expanduser())
    elif isinstance(raw_repos, list):
        config["repos_dir"] = [
            str(Path(entry).expanduser()) for entry in raw_repos if isinstance(entry, str) and entry.strip()
        ]

    _resolve_keychain_secrets(config)

    return config


def get_repos_dirs(config: dict[str, Any]) -> list[str]:
    """Return the configured ``repos_dir`` value as a normalised list.

    Accepts three on-disk shapes, all of which predate the UI:

    * ``repos_dir: "~/Code"``           — legacy single-path string
    * ``repos_dir: ["~/Code", "~/work"]`` — new list form (setup UI writes this)
    * absent / empty                    — returns ``[]``

    Any non-string entries in a list are dropped silently; blank entries are
    skipped. Paths are *not* re-expanded here — callers that round-trip
    through :func:`load_config` already see expanded paths, and callers that
    read the raw config directly (e.g. the setup server) handle expansion
    themselves. Keeping this helper pure-read means it's safe to call from
    probe code that must not mutate the config it inspects.
    """
    raw = config.get("repos_dir")
    if isinstance(raw, str):
        stripped = raw.strip()
        return [stripped] if stripped else []
    if isinstance(raw, list):
        return [entry.strip() for entry in raw if isinstance(entry, str) and entry.strip()]
    return []


_ATLASSIAN_KEYS = ("domain", "email", "api_token")


def get_collector_config(config: dict[str, Any], key: str) -> dict[str, Any]:
    """Return the sub-dict for a specific collector, or empty dict.

    For Atlassian-based collectors (confluence), missing credentials are
    inherited from the shared ``atlassian`` section, then from ``jira``.
    """
    collectors = config.get("collectors", {})
    cfg = dict(collectors.get(key, {}))

    if key in ("confluence",):
        atlassian = collectors.get("atlassian", {})
        jira = collectors.get("jira", {})
        for ak in _ATLASSIAN_KEYS:
            if not cfg.get(ak):
                cfg[ak] = atlassian.get(ak) or jira.get(ak, "")

    return cfg


def is_collector_enabled(config: dict[str, Any], key: str) -> bool:
    """Check whether a collector is enabled in the config."""
    section = get_collector_config(config, key)
    return bool(section.get("enabled", False))
