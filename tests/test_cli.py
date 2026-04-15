"""Tests for the CLI entry point."""

from __future__ import annotations

import pytest

from devjournal.cli import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "devjournal" in out


def test_init_creates_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "devjournal"
    config_path = config_dir / "config.yaml"
    monkeypatch.setattr("devjournal.cli.DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setattr("devjournal.cli.DEFAULT_CONFIG_PATH", config_path)

    main(["init"])

    assert config_path.exists()
    content = config_path.read_text()
    assert "vault_path" in content


def test_init_does_not_overwrite(tmp_path, monkeypatch, capsys):
    config_dir = tmp_path / "devjournal"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("existing: true\n")
    monkeypatch.setattr("devjournal.cli.DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setattr("devjournal.cli.DEFAULT_CONFIG_PATH", config_path)

    main(["init"])

    assert config_path.read_text() == "existing: true\n"
    assert "already exists" in capsys.readouterr().out


def test_invalid_date_exits(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("vault_path: /tmp/vault\ncollectors: {}\n")
    with pytest.raises(SystemExit) as exc:
        main(["-c", str(config_file), "evening", "--date", "not-a-date"])
    assert exc.value.code == 1


def test_evening_dispatches(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"vault_path: {vault}\ncollectors: {{}}\n")

    main(["-c", str(config_file), "evening", "--date", "2026-04-15"])

    note = vault / "Journal" / "Daily" / "2026-04-15.md"
    assert note.exists()


def test_morning_dispatches(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"vault_path: {vault}\ncollectors: {{}}\n")

    main(["-c", str(config_file), "morning", "--date", "2026-04-15"])

    note = vault / "Journal" / "Daily" / "2026-04-15.md"
    assert note.exists()


def test_run_morning_flag(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"vault_path: {vault}\ncollectors: {{}}\n")

    main(["-c", str(config_file), "run", "--morning", "--date", "2026-04-15"])

    note = vault / "Journal" / "Daily" / "2026-04-15.md"
    assert note.exists()
