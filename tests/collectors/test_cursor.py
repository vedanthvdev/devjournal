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


# ---------------------------------------------------------------------------
# Token-redaction regression tests — one per secret prefix in SECURITY.md
# ---------------------------------------------------------------------------


def _redact(text: str) -> str:
    from devjournal.collectors.cursor import _TOKEN_PATTERN

    return _TOKEN_PATTERN.sub("", text)


def test_redacts_gitlab_pat():
    assert "glpat" not in _redact("token is glpat-AbCdEf123456789XYZ please use")


def test_redacts_atlassian_token():
    assert "ATATT" not in _redact("auth ATATT3xFfGF0T1AbCdEfGhIjKlMnOpQrStUv done")


def test_redacts_github_classic_pat():
    assert "ghp_" not in _redact("export TOKEN=ghp_1234567890abcdefghij")


def test_redacts_github_oauth_token():
    assert "gho_" not in _redact("oauth gho_1234567890abcdefghij end")


def test_redacts_github_user_token():
    assert "ghu_" not in _redact("user ghu_1234567890abcdefghij")


def test_redacts_github_server_token():
    assert "ghs_" not in _redact("server ghs_1234567890abcdefghij")


def test_redacts_github_refresh_token():
    assert "ghr_" not in _redact("refresh ghr_1234567890abcdefghij")


def test_redacts_github_fine_grained_pat():
    text = "use github_pat_11AAAAA_BBBBBBBBBBBBBBBBBBBBBB for CI"
    assert "github_pat_" not in _redact(text)


def test_redacts_openai_key():
    assert "sk-proj" not in _redact("OPENAI_API_KEY=sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234")


def test_does_not_redact_scikit_learn():
    """`sk-learn` should not be treated as an OpenAI key."""
    result = _redact("install sk-learn and sk-image for ML work today")
    assert "sk-learn" in result
    assert "sk-image" in result


def test_redacts_bearer_token():
    text = "Authorization: Bearer abc123XYZ_456-789+toolongtopass=="
    assert "Bearer abc123XYZ_456" not in _redact(text)


def test_does_not_redact_bearer_in_prose():
    """`Bearer token authentication` shouldn't eat the next word."""
    result = _redact("Bearer token authentication works well")
    assert "token" in result
    assert "authentication" in result


def test_redacts_slack_bot_token():
    assert "xoxb-" not in _redact("slack xoxb-1234567890-abcdef done")


def test_redacts_slack_user_token():
    assert "xoxp-" not in _redact("xoxp-1234-5678-abcdef here")


def test_redacts_aws_access_key():
    assert "AKIA" not in _redact("export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")


def test_does_not_redact_lowercase_akia_prose():
    """Real AWS keys are uppercase only — lowercase akia… must not match."""
    result = _redact("the word akiaPQRSTUVWXYZ1234567 is not a key")
    assert "akia" in result.lower()


def test_redacts_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NSIsIm5hbWUiOiJBbGljZSJ9."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    redacted = _redact(f"token {jwt} end")
    assert "eyJ" not in redacted


def test_does_not_redact_lowercase_eyj():
    """JWT headers always start with literal `eyJ`."""
    result = _redact("the variable eyj_value is not a JWT placeholder text here")
    assert "eyj" in result.lower()


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
