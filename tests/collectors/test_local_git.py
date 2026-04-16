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


def test_collect_scans_multiple_dirs(tmp_path):
    """With ``repos_dir`` as a list, commits from every root end up in the
    result — unique repo names are reported bare, not prefixed.
    """
    root_a = tmp_path / "code"
    root_b = tmp_path / "work"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "alpha").mkdir()
    (root_a / "alpha" / ".git").mkdir()
    (root_b / "beta").mkdir()
    (root_b / "beta" / ".git").mkdir()

    def fake_run(args, **kwargs):
        # ``cwd`` tells us which repo we're scanning — return distinct output
        # so the assertion can tell the two rows apart.
        cwd = kwargs.get("cwd", "")
        if "alpha" in cwd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="a1 from alpha\n")
        if "beta" in cwd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="b1 from beta\n")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")

    with patch("subprocess.run", side_effect=fake_run):
        collector = LocalGitCollector()
        result = collector.collect(date(2026, 4, 15), {
            "repos_dir": [str(root_a), str(root_b)],
            "author_email": "me@test.com",
        })

    projects = sorted(item["project"] for item in result.items)
    assert projects == ["alpha", "beta"], projects
    messages = sorted(item["message"] for item in result.items)
    assert messages == ["from alpha", "from beta"]


def test_collect_skips_missing_dir_in_list(tmp_path):
    """A missing root in a list of roots must not prevent scanning the others.
    This is the user-facing behaviour of "I moved one of my code folders
    yesterday and forgot to update config" — the other folders keep working.
    """
    missing = tmp_path / "gone"
    real = tmp_path / "here"
    real.mkdir()
    repo = real / "proj"
    repo.mkdir()
    (repo / ".git").mkdir()

    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc fixed thing\n")
    with patch("subprocess.run", return_value=fake_result):
        collector = LocalGitCollector()
        result = collector.collect(date(2026, 4, 15), {
            "repos_dir": [str(missing), str(real)],
            "author_email": "me@test.com",
        })
    assert [item["project"] for item in result.items] == ["proj"]


def test_collect_disambiguates_name_collisions_across_roots(tmp_path):
    """Two directories named ``foo`` under different roots must not silently
    merge into a single row — the display label gets the root appended so
    the user can tell them apart in the evening note.
    """
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "foo").mkdir()
    (root_a / "foo" / ".git").mkdir()
    (root_b / "foo").mkdir()
    (root_b / "foo" / ".git").mkdir()

    def fake_run(args, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        if cwd.startswith(str(root_a)):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="a1 from A\n")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="b1 from B\n")

    with patch("subprocess.run", side_effect=fake_run):
        collector = LocalGitCollector()
        result = collector.collect(date(2026, 4, 15), {
            "repos_dir": [str(root_a), str(root_b)],
            "author_email": "me@test.com",
        })

    projects = sorted(item["project"] for item in result.items)
    assert len(projects) == 2, projects
    # Exactly one row per root, each annotated with its root path.
    assert all(p.startswith("foo (") for p in projects), projects
    assert any(str(root_a) in p for p in projects)
    assert any(str(root_b) in p for p in projects)
