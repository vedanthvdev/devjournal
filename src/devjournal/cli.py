"""Command-line interface for devjournal.

Usage:
    devjournal morning           # Populate today's agenda
    devjournal evening           # Populate today's work log (default)
    devjournal run               # Alias for evening
    devjournal run --morning     # Alias for morning
    devjournal run --date 2026-04-15  # Run for a specific date
    devjournal init              # Create config file from template
    devjournal schedule install  # Install OS-level scheduling (launchd / cron)
    devjournal schedule remove   # Remove installed schedule
"""

from __future__ import annotations

import argparse
import importlib.resources
import logging
import shutil
import sys
from datetime import date
from pathlib import Path

from devjournal import __version__
from devjournal.config import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH, load_config
from devjournal.engine import Engine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="devjournal",
        description="Automated daily work journals for engineers.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"devjournal {__version__}")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: ~/.config/devjournal/config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    sub = parser.add_subparsers(dest="command")

    # -- init --
    sub.add_parser("init", help="Create a config file from the example template")

    # -- morning --
    morning_p = sub.add_parser("morning", help="Populate today's morning agenda")
    morning_p.add_argument("--date", type=str, default=None)

    # -- evening --
    evening_p = sub.add_parser("evening", help="Populate today's work log")
    evening_p.add_argument("--date", type=str, default=None)

    # -- run (flexible shortcut) --
    run_p = sub.add_parser("run", help="Run morning or evening mode")
    run_p.add_argument("--morning", action="store_true")
    run_p.add_argument("--date", type=str, default=None)

    # -- schedule --
    schedule_p = sub.add_parser("schedule", help="Manage OS-level scheduling")
    schedule_sub = schedule_p.add_subparsers(dest="schedule_action")
    schedule_sub.add_parser("install", help="Install morning + evening schedule")
    schedule_sub.add_parser("remove", help="Remove installed schedule")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.command == "init":
        _cmd_init()
    elif args.command == "schedule":
        _cmd_schedule(args)
    elif args.command in ("morning", "evening", "run", None):
        _cmd_run(args)
    else:
        parser.print_help()


def _cmd_init() -> None:
    """Copy the example config into ~/.config/devjournal/config.yaml."""
    if DEFAULT_CONFIG_PATH.exists():
        print(f"Config already exists: {DEFAULT_CONFIG_PATH}")
        print("Edit it directly or delete it to re-initialise.")
        return

    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    example = importlib.resources.files("devjournal") / "config.example.yaml"
    shutil.copy2(str(example), str(DEFAULT_CONFIG_PATH))
    DEFAULT_CONFIG_PATH.chmod(0o600)
    print(f"Created config: {DEFAULT_CONFIG_PATH}")
    print("Edit it with your API tokens, then run: devjournal evening")


def _cmd_run(args: argparse.Namespace) -> None:
    """Execute a morning or evening run."""
    config = load_config(args.config)
    engine = Engine(config)

    target = date.fromisoformat(args.date) if getattr(args, "date", None) else date.today()
    is_morning = args.command == "morning" or getattr(args, "morning", False)

    if is_morning:
        engine.run_morning(target)
    else:
        engine.run_evening(target)


def _cmd_schedule(args: argparse.Namespace) -> None:
    """Install or remove OS-level scheduling."""
    from devjournal.scheduler import install_schedule, remove_schedule

    config = load_config(args.config)

    if args.schedule_action == "install":
        install_schedule(config)
    elif args.schedule_action == "remove":
        remove_schedule()
    else:
        print("Usage: devjournal schedule [install|remove]")
        sys.exit(1)
