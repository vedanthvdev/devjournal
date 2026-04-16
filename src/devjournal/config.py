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

    if config.get("repos_dir"):
        config["repos_dir"] = str(Path(config["repos_dir"]).expanduser())

    return config


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
