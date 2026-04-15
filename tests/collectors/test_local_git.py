"""Tests for the local git collector."""

from __future__ import annotations

import subprocess
from datetime import date
from unittest.mock import patch

from devjournal.collectors.local_git import LocalGitCollector


def test_collect_finds_commits(tmp_path):
    repos = tmp_path / "repos"
    repos.mkdir()
    repo = repos / "my-project"
    repo.mkdir()
    (repo / ".git").mkdir()

    git_output = "abc1234 fix authentication\ndef5678 add unit tests\n"
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=git_output)

    with patch("subprocess.run", return_value=mock_result):
        collector = LocalGitCollector()
        result = collector.collect(date(2026, 4, 15), {
            "repos_dir": str(repos),
            "author_email": "me@test.com",
        })

    assert result.section_id == "code_changes"
    assert len(result.items) == 2
    assert result.items[0]["project"] == "my-project"
    assert result.items[0]["message"] == "fix authentication"


def test_collect_no_repos_dir(tmp_path):
    collector = LocalGitCollector()
    result = collector.collect(date(2026, 4, 15), {
        "repos_dir": str(tmp_path / "nonexistent"),
        "author_email": "me@test.com",
    })
    assert result.items == []


def test_collect_skips_non_git_dirs(tmp_path):
    repos = tmp_path / "repos"
    repos.mkdir()
    (repos / "not-a-repo").mkdir()

    collector = LocalGitCollector()
    result = collector.collect(date(2026, 4, 15), {
        "repos_dir": str(repos),
        "author_email": "me@test.com",
    })
    assert result.items == []


def test_collect_handles_git_timeout(tmp_path):
    repos = tmp_path / "repos"
    repos.mkdir()
    repo = repos / "slow-repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
        collector = LocalGitCollector()
        result = collector.collect(date(2026, 4, 15), {
            "repos_dir": str(repos),
            "author_email": "me@test.com",
        })
    assert result.items == []
