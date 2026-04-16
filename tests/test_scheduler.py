"""Tests for the scheduler module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from devjournal.scheduler import _PLIST_TEMPLATE, _WEEKDAY_DICT, _parse_time


def _build_plist(mode: str, hour: int, minute: int, weekdays_only: bool = True):
    """Reproduce the plist generation logic for testing."""
    days = range(1, 6) if weekdays_only else range(0, 7)
    weekday_dicts = "".join(
        _WEEKDAY_DICT.format(day=d, hour=hour, minute=minute) for d in days
    )
    return _PLIST_TEMPLATE.format(
        label=f"com.devjournal.{mode}",
        python="/usr/bin/python3",
        mode=mode,
        weekday_dicts=weekday_dicts,
        log_dir="/tmp/logs",
        home="/Users/test",
    )


def test_plist_contains_correct_time():
    plist = _build_plist("morning", 8, 30)
    assert "<integer>8</integer>" in plist
    assert "<integer>30</integer>" in plist
    assert "com.devjournal.morning" in plist


def test_plist_weekdays_only():
    plist = _build_plist("evening", 17, 0, weekdays_only=True)
    for day in range(1, 6):
        assert f"<integer>{day}</integer>" in plist
    assert plist.count("<key>Weekday</key>") == 5


def test_plist_all_days():
    plist = _build_plist("morning", 9, 0, weekdays_only=False)
    assert plist.count("<key>Weekday</key>") == 7


def test_plist_valid_xml():
    plist = _build_plist("evening", 17, 0)
    assert plist.startswith("<?xml version=")
    assert "</plist>" in plist


def test_cron_line_format():
    from devjournal.scheduler import _CRON_MARKER

    minute, hour, dow = 30, 8, "1-5"
    line = f"{minute} {hour} * * {dow} /usr/bin/python3 -m devjournal morning {_CRON_MARKER}"
    assert "30 8 * * 1-5" in line
    assert _CRON_MARKER in line


def test_install_schedule_unsupported_os(sample_config):
    from devjournal.scheduler import install_schedule

    with patch("devjournal.scheduler.platform.system", return_value="FreeBSD"):
        with pytest.raises(SystemExit):
            install_schedule(sample_config)


def test_install_launchd(tmp_path, sample_config, monkeypatch):
    from devjournal.scheduler import _install_launchd

    launchd_dir = tmp_path / "LaunchAgents"
    launchd_dir.mkdir()
    monkeypatch.setattr("devjournal.scheduler._LAUNCHD_DIR", launchd_dir)

    with patch("devjournal.scheduler.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0})()
        _install_launchd(sample_config)

    morning_plist = launchd_dir / "com.devjournal.morning.plist"
    evening_plist = launchd_dir / "com.devjournal.evening.plist"
    assert morning_plist.exists()
    assert evening_plist.exists()

    content = morning_plist.read_text()
    assert "<integer>8</integer>" in content
    assert "<integer>30</integer>" in content


def test_parse_time_valid():
    assert _parse_time("08:30") == (8, 30)
    assert _parse_time("0:00") == (0, 0)
    assert _parse_time("23:59") == (23, 59)


def test_parse_time_invalid_format():
    with pytest.raises(ValueError, match="Invalid time format"):
        _parse_time("nope")
    with pytest.raises(ValueError, match="Invalid time format"):
        _parse_time("8:30:00")


def test_parse_time_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        _parse_time("25:00")
    with pytest.raises(ValueError, match="out of range"):
        _parse_time("08:60")
