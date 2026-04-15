"""Tests for the Cursor collector's helper functions."""

from __future__ import annotations

from devjournal.collectors.cursor import (
    _clean_query,
    _extract_project_name,
    _group_sessions,
    _pick_summary,
)


def test_extract_project_name_code_suffix():
    assert _extract_project_name("Users-alice-Code-backend") == "backend"


def test_extract_project_name_nested():
    assert _extract_project_name("Users-alice-Code-myapp-backend") == "myapp-backend"


def test_extract_project_name_idea_projects():
    assert _extract_project_name("Users-bob-IdeaProjects-webapp") == "webapp"


def test_extract_project_name_fallback():
    assert _extract_project_name("something-random") == "random"


def test_clean_query_truncates_long():
    long_q = "a " * 100
    result = _clean_query(long_q)
    assert result is not None
    assert len(result) <= 83  # 80 + "..."


def test_clean_query_removes_tokens():
    q = "deploy using glpat-abc123xyz and go"
    result = _clean_query(q)
    assert result is not None
    assert "glpat" not in result


def test_clean_query_rejects_short():
    assert _clean_query("hi") is None


def test_pick_summary_prefers_action():
    queries = ["hello there", "implement the new auth flow", "thanks"]
    assert "implement" in _pick_summary(queries).lower()


def test_pick_summary_fallback():
    queries = ["what is going on with the server today"]
    result = _pick_summary(queries)
    assert "server" in result.lower()


def test_pick_summary_empty():
    assert _pick_summary([]) == "Cursor session"


# ---------------------------------------------------------------------------
# _group_sessions tests
# ---------------------------------------------------------------------------


def test_group_sessions_keeps_large_standalone():
    sessions = [
        {"project": "backend", "summary": "Big refactor", "queries": 10, "tool_calls": 200, "files": ["a.py"]},
    ]
    result = _group_sessions(sessions)
    assert len(result) == 1
    assert result[0]["summary"] == "Big refactor"


def test_group_sessions_merges_small_same_project():
    sessions = [
        {"project": "infra", "summary": "Review config", "queries": 1, "tool_calls": 5, "files": ["a.yml"]},
        {"project": "infra", "summary": "Review deploy", "queries": 1, "tool_calls": 8, "files": ["b.yml"]},
        {"project": "infra", "summary": "Check logs", "queries": 1, "tool_calls": 3, "files": ["a.yml"]},
    ]
    result = _group_sessions(sessions)
    assert len(result) == 1
    assert "+2 related sessions" in result[0]["summary"]
    assert result[0]["queries"] == 3
    assert result[0]["tool_calls"] == 16
    assert "a.yml" in result[0]["files"]
    assert "b.yml" in result[0]["files"]


def test_group_sessions_single_small_stays_standalone():
    sessions = [
        {"project": "backend", "summary": "Quick check", "queries": 1, "tool_calls": 2, "files": []},
    ]
    result = _group_sessions(sessions)
    assert len(result) == 1
    assert "related" not in result[0]["summary"]


def test_group_sessions_mixed_large_and_small():
    sessions = [
        {"project": "api", "summary": "Big feature", "queries": 5, "tool_calls": 100, "files": ["x.py"]},
        {"project": "api", "summary": "Quick fix", "queries": 1, "tool_calls": 3, "files": ["y.py"]},
        {"project": "api", "summary": "Another fix", "queries": 1, "tool_calls": 4, "files": ["z.py"]},
    ]
    result = _group_sessions(sessions)
    assert len(result) == 2
    large = [r for r in result if r["summary"] == "Big feature"]
    grouped = [r for r in result if "related" in r["summary"]]
    assert len(large) == 1
    assert len(grouped) == 1


def test_group_sessions_deduplicates_files():
    sessions = [
        {"project": "svc", "summary": "Review A", "queries": 1, "tool_calls": 5, "files": ["f.py", "g.py"]},
        {"project": "svc", "summary": "Review B", "queries": 1, "tool_calls": 5, "files": ["f.py"]},
    ]
    result = _group_sessions(sessions)
    assert len(result) == 1
    assert result[0]["files"].count("f.py") == 1
