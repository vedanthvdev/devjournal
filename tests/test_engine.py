"""Tests for the Engine orchestrator."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from devjournal.collector import CollectorResult
from devjournal.engine import Engine, _section_is_empty


def _make_config(tmp_path, enabled_collectors=None):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    collectors = {}
    for key in (enabled_collectors or []):
        collectors[key] = {"enabled": True}
    return {
        "vault_path": str(vault),
        "repos_dir": str(tmp_path / "repos"),
        "collectors": collectors,
    }


def test_engine_discovers_enabled_collectors(tmp_path):
    config = _make_config(tmp_path, ["local_git", "cursor"])
    engine = Engine(config)
    names = [c.name for c in engine._collectors]
    assert "local_git" in names
    assert "cursor" in names
    assert "jira" not in names


def test_engine_skips_disabled_collectors(tmp_path):
    config = _make_config(tmp_path, [])
    engine = Engine(config)
    assert engine._collectors == []


def test_run_evening_creates_note(tmp_path):
    config = _make_config(tmp_path, [])
    engine = Engine(config)
    target = date(2026, 4, 15)
    engine.run_evening(target)
    note = tmp_path / "vault" / "Journal" / "Daily" / "2026-04-15.md"
    assert note.exists()
    content = note.read_text()
    assert "daily_note" in content


def test_run_morning_creates_note(tmp_path):
    config = _make_config(tmp_path, [])
    engine = Engine(config)
    target = date(2026, 4, 15)
    engine.run_morning(target)
    note = tmp_path / "vault" / "Journal" / "Daily" / "2026-04-15.md"
    assert note.exists()


def test_engine_handles_collector_failure(tmp_path):
    """A failing collector should not crash the engine."""
    config = _make_config(tmp_path, ["local_git"])
    engine = Engine(config)
    target = date(2026, 4, 15)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    with patch.object(engine._collectors[0], "collect", side_effect=_boom):
        engine.run_evening(target)

    note = tmp_path / "vault" / "Journal" / "Daily" / "2026-04-15.md"
    assert note.exists()


def test_engine_merges_same_section_id(tmp_path):
    """Two collectors producing the same section_id should have items merged."""
    config = _make_config(tmp_path, ["gitlab", "local_git"])
    engine = Engine(config)
    target = date(2026, 4, 15)

    gitlab_result = CollectorResult(
        section_id="code_changes",
        heading="### Code Changes",
        items=[{"type": "push", "project": "backend", "message": "fix bug"}],
    )
    local_result = CollectorResult(
        section_id="code_changes",
        heading="### Code Changes",
        items=[{"type": "commit", "project": "frontend", "message": "add page"}],
    )

    gitlab_collector = next(c for c in engine._collectors if c.name == "gitlab")
    local_collector = next(c for c in engine._collectors if c.name == "local_git")

    with (
        patch.object(gitlab_collector, "collect", return_value=gitlab_result),
        patch.object(local_collector, "collect", return_value=local_result),
    ):
        results = engine._collect_all(target)

    code_results = [r for r in results if r.section_id == "code_changes"]
    assert len(code_results) == 1
    assert len(code_results[0].items) == 2


def test_engine_merge_does_not_mutate_originals(tmp_path):
    """Merging should not modify the original CollectorResult objects."""
    config = _make_config(tmp_path, ["gitlab", "local_git"])
    engine = Engine(config)
    target = date(2026, 4, 15)

    gitlab_result = CollectorResult(
        section_id="code_changes",
        heading="### Code Changes",
        items=[{"type": "push", "project": "backend"}],
    )
    local_result = CollectorResult(
        section_id="code_changes",
        heading="### Code Changes",
        items=[{"type": "commit", "project": "frontend"}],
    )

    gitlab_collector = next(c for c in engine._collectors if c.name == "gitlab")
    local_collector = next(c for c in engine._collectors if c.name == "local_git")

    with (
        patch.object(gitlab_collector, "collect", return_value=gitlab_result),
        patch.object(local_collector, "collect", return_value=local_result),
    ):
        engine._collect_all(target)

    assert len(gitlab_result.items) == 1
    assert len(local_result.items) == 1


def test_section_is_empty_with_placeholder():
    content = '<!-- BEGIN:jira_active -->\n### Jira Tickets\n*No activity.*\n<!-- END:jira_active -->'
    assert _section_is_empty(content, "jira_active") is True


def test_section_is_empty_with_no_active_tickets():
    content = '<!-- BEGIN:jira_active -->\n### Jira Tickets\n*No active tickets found.*\n<!-- END:jira_active -->'
    assert _section_is_empty(content, "jira_active") is True


def test_section_is_not_empty_with_user_italic():
    """User-written italic text like *this is important* should not be a placeholder."""
    content = '<!-- BEGIN:notes -->\n### Notes\n*this is important*\n<!-- END:notes -->'
    assert _section_is_empty(content, "notes") is False


def test_section_is_empty_with_real_content():
    content = '<!-- BEGIN:jira_active -->\n### Jira Tickets\n- CAR-123 task\n<!-- END:jira_active -->'
    assert _section_is_empty(content, "jira_active") is False


def test_section_is_empty_missing_section():
    assert _section_is_empty("no markers here", "jira_active") is True


def test_section_is_empty_does_not_match_bold_text():
    """Bold markdown like **In Progress** must not be mistaken for a placeholder."""
    content = (
        '<!-- BEGIN:jira_active -->\n'
        '### Jira Tickets\n'
        '- **backend**: 2 commits\n'
        '<!-- END:jira_active -->'
    )
    assert _section_is_empty(content, "jira_active") is False
