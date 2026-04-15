"""Tests for the markdown formatter."""

from __future__ import annotations

from devjournal.collector import CollectorResult
from devjournal.formatter import format_carry_forward, format_result


def test_format_empty_result():
    result = CollectorResult(
        section_id="jira_activity",
        heading="### Jira Activity",
        items=[],
        empty_message="No Jira activity today.",
    )
    md = format_result(result)
    assert "### Jira Activity" in md
    assert "*No Jira activity today.*" in md


def test_format_jira_active():
    result = CollectorResult(
        section_id="jira_active",
        heading="### Jira Tickets (Active)",
        items=[
            {"key": "PROJ-1", "summary": "Fix bug", "status": "In Progress", "link": "https://x/PROJ-1"},
            {"key": "PROJ-2", "summary": "Add feature", "status": "To Do", "link": "https://x/PROJ-2"},
        ],
    )
    md = format_result(result)
    assert "[PROJ-1]" in md
    assert "Fix bug" in md
    assert "**In Progress**" in md


def test_format_code_changes_with_commits():
    result = CollectorResult(
        section_id="code_changes",
        heading="### Code Changes",
        items=[
            {"type": "commit", "project": "backend", "message": "fix auth"},
            {"type": "commit", "project": "backend", "message": "add tests"},
            {"type": "push", "project": "frontend", "message": "update UI"},
        ],
    )
    md = format_result(result)
    assert "**backend**: 2 commits" in md
    assert "**frontend**: 1 commit" in md
    assert "fix auth" in md


def test_format_code_changes_with_prs():
    result = CollectorResult(
        section_id="code_changes",
        heading="### Code Changes",
        items=[
            {"type": "pr", "project": "api", "action": "opened", "title": "Add pagination"},
        ],
    )
    md = format_result(result)
    assert "Pull Requests" in md
    assert "Add pagination" in md


def test_format_cursor_sessions():
    result = CollectorResult(
        section_id="cursor_sessions",
        heading="### Cursor Sessions",
        items=[
            {
                "project": "myapp",
                "summary": "Implement auth flow",
                "files": ["auth.py", "views.py"],
                "queries": 5,
                "tool_calls": 42,
            },
        ],
    )
    md = format_result(result)
    assert "**myapp**: Implement auth flow" in md
    assert "(5 queries, 42 tool calls)" in md
    assert "`auth.py`" in md


def test_format_carry_forward_empty():
    md = format_carry_forward([])
    assert "Nothing carried forward" in md


def test_format_carry_forward_items():
    md = format_carry_forward(["- [ ] Task A", "- [ ] Task B"])
    assert "Task A" in md
    assert "Task B" in md
    assert "Carried Forward" in md


def test_format_generic_fallback():
    result = CollectorResult(
        section_id="custom_thing",
        heading="### Custom",
        items=[
            {"title": "Item A", "link": "https://example.com"},
            {"title": "Item B"},
        ],
    )
    md = format_result(result)
    assert "[Item A](https://example.com)" in md
    assert "- Item B" in md
