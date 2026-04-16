# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""OS-level scheduling — generates and installs launchd plists (macOS) or cron jobs (Linux)."""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("devjournal")

_LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"
_PLIST_PREFIX = "com.devjournal"


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse an ``HH:MM`` string into (hour, minute), raising on invalid input."""
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: '{time_str}'. Expected HH:MM.")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range: '{time_str}'. Hour must be 0-23, minute 0-59.")
    return hour, minute


def install_schedule(config: dict[str, Any]) -> None:
    """Detect the OS and install the appropriate schedule."""
    system = platform.system()
    if system == "Darwin":
        _install_launchd(config)
    elif system == "Linux":
        _install_cron(config)
    else:
        log.error("Unsupported OS for scheduling: %s", system)
        sys.exit(1)


def remove_schedule() -> None:
    """Remove the installed schedule."""
    system = platform.system()
    if system == "Darwin":
        _remove_launchd()
    elif system == "Linux":
        _remove_cron()
    else:
        log.error("Unsupported OS: %s", system)


# ---------------------------------------------------------------------------
# macOS launchd
# ---------------------------------------------------------------------------

_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>devjournal</string>
        <string>{mode}</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>{weekday_dicts}
    </array>
    <key>StandardOutPath</key>
    <string>{log_dir}/{mode}.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/{mode}.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>{home}</string>
    </dict>
</dict>
</plist>
"""

_WEEKDAY_DICT = """
        <dict>
            <key>Weekday</key>
            <integer>{day}</integer>
            <key>Hour</key>
            <integer>{hour}</integer>
            <key>Minute</key>
            <integer>{minute}</integer>
        </dict>"""


def _install_launchd(config: dict[str, Any]) -> None:
    schedule = config.get("schedule", {})
    morning_time = schedule.get("morning", "08:30")
    evening_time = schedule.get("evening", "17:00")
    weekdays_only = schedule.get("weekdays_only", True)

    python_path = sys.executable
    home = str(Path.home())
    log_dir = str(Path.home() / ".config" / "devjournal")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    days = range(1, 6) if weekdays_only else range(0, 7)

    for mode, time_str in [("morning", morning_time), ("evening", evening_time)]:
        hour, minute = _parse_time(time_str)
        label = f"{_PLIST_PREFIX}.{mode}"
        weekday_dicts = "".join(
            _WEEKDAY_DICT.format(day=d, hour=hour, minute=minute) for d in days
        )
        plist = _PLIST_TEMPLATE.format(
            label=label,
            python=python_path,
            mode=mode,
            weekday_dicts=weekday_dicts,
            log_dir=log_dir,
            home=home,
        )
        plist_path = _LAUNCHD_DIR / f"{label}.plist"
        _LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

        # Unload first if already loaded
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)

        plist_path.write_text(plist)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        log.info("Installed launchd schedule: %s at %s", label, time_str)

    print("Schedule installed. Morning and evening runs configured.")
    print(f"Logs: {log_dir}/morning.log and {log_dir}/evening.log")


def _remove_launchd() -> None:
    for mode in ("morning", "evening"):
        label = f"{_PLIST_PREFIX}.{mode}"
        plist_path = _LAUNCHD_DIR / f"{label}.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.unlink()
            log.info("Removed launchd schedule: %s", label)
    print("Schedule removed.")


# ---------------------------------------------------------------------------
# Linux cron
# ---------------------------------------------------------------------------

_CRON_MARKER = "# devjournal-auto"


def _install_cron(config: dict[str, Any]) -> None:
    schedule = config.get("schedule", {})
    morning_time = schedule.get("morning", "08:30")
    evening_time = schedule.get("evening", "17:00")
    weekdays_only = schedule.get("weekdays_only", True)

    python_path = sys.executable
    dow = "1-5" if weekdays_only else "*"

    lines: list[str] = []
    for mode, time_str in [("morning", morning_time), ("evening", evening_time)]:
        hour, minute = _parse_time(time_str)
        lines.append(
            f"{minute} {hour} * * {dow} {python_path} -m devjournal {mode} {_CRON_MARKER}"
        )

    # Read existing crontab, strip old devjournal entries, append new ones
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = [
            line for line in result.stdout.splitlines() if _CRON_MARKER not in line
        ]
    except Exception:
        existing = []

    new_crontab = "\n".join(existing + lines) + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode == 0:
        print("Cron schedule installed.")
    else:
        log.error("Failed to install cron: %s", proc.stderr)


def _remove_cron() -> None:
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        cleaned = [line for line in result.stdout.splitlines() if _CRON_MARKER not in line]
        new_crontab = "\n".join(cleaned) + "\n" if cleaned else ""
        subprocess.run(["crontab", "-"], input=new_crontab, text=True)
        print("Cron entries removed.")
    except Exception as e:
        log.error("Failed to remove cron entries: %s", e)
