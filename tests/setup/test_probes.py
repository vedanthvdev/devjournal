"""Tests for devjournal.setup.probes.

HTTP probes are mocked via the ``responses`` library. The git probe uses a
real temp git repo so we exercise the actual subprocess path.
"""

from __future__ import annotations

import subprocess

import pytest
import responses

from devjournal.setup.probes import (
    probe_confluence,
    probe_cursor,
    probe_github,
    probe_gitlab,
    probe_jira,
    probe_local_git,
)


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------


@responses.activate
def test_jira_success():
    responses.get(
        "https://test.atlassian.net/rest/api/3/myself",
        json={"emailAddress": "user@test.com", "displayName": "Test User"},
        status=200,
    )
    result = probe_jira({"domain": "test.atlassian.net", "email": "user@test.com", "api_token": "t"})
    assert result.ok
    assert "user@test.com" in result.detail


@responses.activate
def test_jira_auth_failure():
    responses.get(
        "https://test.atlassian.net/rest/api/3/myself",
        status=401,
    )
    result = probe_jira({"domain": "test.atlassian.net", "email": "u@t.com", "api_token": "bad"})
    assert not result.ok
    assert "Authentication" in result.detail


def test_jira_missing_fields():
    result = probe_jira({"domain": "", "email": "", "api_token": ""})
    assert not result.ok
    assert "required" in result.detail.lower()


# ---------------------------------------------------------------------------
# Confluence
# ---------------------------------------------------------------------------


@responses.activate
def test_confluence_success():
    responses.get(
        "https://test.atlassian.net/wiki/rest/api/user/current",
        json={"accountId": "abc"},
        status=200,
    )
    result = probe_confluence({"domain": "test.atlassian.net", "email": "u@t.com", "api_token": "t"})
    assert result.ok


def test_confluence_without_atlassian_creds():
    result = probe_confluence({"domain": "", "email": "", "api_token": ""})
    assert not result.ok
    assert "Jira" in result.detail


# ---------------------------------------------------------------------------
# GitLab
# ---------------------------------------------------------------------------


@responses.activate
def test_gitlab_success():
    responses.get(
        "https://gitlab.example.com/api/v4/user",
        json={"username": "alice"},
        status=200,
    )
    result = probe_gitlab(
        {"url": "https://gitlab.example.com", "token": "glpat-x", "username": "alice"},
    )
    assert result.ok
    assert "alice" in result.detail


@responses.activate
def test_gitlab_username_mismatch():
    responses.get(
        "https://gitlab.example.com/api/v4/user",
        json={"username": "bob"},
        status=200,
    )
    result = probe_gitlab(
        {"url": "https://gitlab.example.com", "token": "glpat-x", "username": "alice"},
    )
    assert not result.ok
    assert "alice" in result.detail and "bob" in result.detail


@responses.activate
def test_gitlab_timeout():
    responses.get(
        "https://gitlab.example.com/api/v4/user",
        body=ConnectionError("broken"),
    )
    result = probe_gitlab({"url": "https://gitlab.example.com", "token": "x", "username": "a"})
    assert not result.ok


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


@responses.activate
def test_github_success_case_insensitive_username():
    responses.get(
        "https://api.github.com/user",
        json={"login": "Alice"},
        status=200,
    )
    result = probe_github({"token": "ghp_x", "username": "alice"})
    assert result.ok


@responses.activate
def test_github_username_mismatch():
    responses.get(
        "https://api.github.com/user",
        json={"login": "someoneelse"},
        status=200,
    )
    result = probe_github({"token": "ghp_x", "username": "alice"})
    assert not result.ok


def test_github_missing_token():
    assert not probe_github({"token": ""}).ok


# ---------------------------------------------------------------------------
# Local git
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_repo(tmp_path):
    """A parent directory containing one real git repo with a commit by the author."""
    parent = tmp_path / "repos"
    parent.mkdir()
    repo = parent / "myrepo"
    repo.mkdir()

    def run(*args):
        subprocess.run(args, cwd=repo, check=True, capture_output=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "probe@test.com")
    run("git", "config", "user.name", "Probe")
    (repo / "file.txt").write_text("hi")
    run("git", "add", ".")
    run("git", "commit", "-q", "-m", "initial", "--author=Probe <probe@test.com>")

    return parent


def test_local_git_finds_commits(git_repo):
    result = probe_local_git(
        {"author_email": "probe@test.com"}, repos_dir=str(git_repo),
    )
    assert result.ok
    assert "myrepo" in result.detail or "commits" in result.detail.lower()


def test_local_git_no_matches(git_repo):
    result = probe_local_git(
        {"author_email": "nobody@test.com"}, repos_dir=str(git_repo),
    )
    assert not result.ok


def test_local_git_missing_email():
    result = probe_local_git({"author_email": ""}, repos_dir="/tmp")
    assert not result.ok


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


def test_cursor_detection_returns_result():
    # We can't mock the real user's filesystem, but the call must not raise
    # and must return a well-formed result.
    result = probe_cursor({})
    assert isinstance(result.ok, bool)
    assert isinstance(result.detail, str)
