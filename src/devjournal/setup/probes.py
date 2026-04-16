# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Connection probes used by the setup UI's "Test connection" buttons.

Each probe issues a single authenticated request against a lightweight
identity endpoint (``/myself``, ``/user``, etc.) so the user gets a
green-tick confirmation before saving. Failures return a short, human
message — we deliberately do not echo raw HTTP bodies back to the browser
because they can contain tokens or server fingerprinting.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("devjournal")

_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "detail": self.detail}


def _http_failure(exc: Exception) -> ProbeResult:
    """Render a requests exception as a safe, user-facing message."""
    if isinstance(exc, requests.Timeout):
        return ProbeResult(False, f"Timeout after {_TIMEOUT_SECONDS}s")
    if isinstance(exc, requests.ConnectionError):
        return ProbeResult(False, "Could not reach host — check URL / network")
    return ProbeResult(False, "Request failed")


def _status_failure(resp: requests.Response) -> ProbeResult:
    if resp.status_code in (401, 403):
        return ProbeResult(False, "Authentication failed — check token and email")
    if resp.status_code == 404:
        return ProbeResult(False, "Endpoint not found — check URL")
    return ProbeResult(False, f"Unexpected status {resp.status_code}")


# ---------------------------------------------------------------------------
# Per-integration probes
# ---------------------------------------------------------------------------


def probe_jira(config: dict) -> ProbeResult:
    domain = (config.get("domain") or "").strip()
    email = (config.get("email") or "").strip()
    token = (config.get("api_token") or "").strip()
    if not (domain and email and token):
        return ProbeResult(False, "Domain, email, and API token are required")
    url = f"https://{domain}/rest/api/3/myself"
    try:
        resp = requests.get(url, auth=(email, token), timeout=_TIMEOUT_SECONDS)
    except Exception as exc:
        return _http_failure(exc)
    if resp.status_code != 200:
        return _status_failure(resp)
    try:
        who = resp.json().get("emailAddress") or resp.json().get("displayName") or email
    except Exception:
        who = email
    return ProbeResult(True, f"Authenticated as {who}")


def probe_confluence(config: dict) -> ProbeResult:
    # Confluence inherits auth from Jira/Atlassian — the caller passes us the
    # already-merged config dict from ``get_collector_config``.
    domain = (config.get("domain") or "").strip()
    email = (config.get("email") or "").strip()
    token = (config.get("api_token") or "").strip()
    if not (domain and email and token):
        return ProbeResult(False, "Confluence uses Atlassian credentials — fill Jira first")
    url = f"https://{domain}/wiki/rest/api/user/current"
    try:
        resp = requests.get(url, auth=(email, token), timeout=_TIMEOUT_SECONDS)
    except Exception as exc:
        return _http_failure(exc)
    if resp.status_code != 200:
        return _status_failure(resp)
    return ProbeResult(True, "Confluence reachable")


def probe_gitlab(config: dict) -> ProbeResult:
    url = (config.get("url") or "").rstrip("/")
    token = (config.get("token") or "").strip()
    expected_user = (config.get("username") or "").strip()
    if not (url and token):
        return ProbeResult(False, "URL and token are required")
    try:
        resp = requests.get(
            f"{url}/api/v4/user",
            headers={"PRIVATE-TOKEN": token},
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return _http_failure(exc)
    if resp.status_code != 200:
        return _status_failure(resp)
    try:
        username = resp.json().get("username", "")
    except Exception:
        username = ""
    if expected_user and username and username != expected_user:
        return ProbeResult(
            False,
            f"Token belongs to '{username}', but config says '{expected_user}'",
        )
    return ProbeResult(True, f"Authenticated as {username or 'user'}")


def probe_github(config: dict) -> ProbeResult:
    token = (config.get("token") or "").strip()
    expected_user = (config.get("username") or "").strip()
    if not token:
        return ProbeResult(False, "Token is required")
    try:
        resp = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return _http_failure(exc)
    if resp.status_code != 200:
        return _status_failure(resp)
    try:
        login = resp.json().get("login", "")
    except Exception:
        login = ""
    if expected_user and login and login.lower() != expected_user.lower():
        return ProbeResult(
            False,
            f"Token belongs to '{login}', but config says '{expected_user}'",
        )
    return ProbeResult(True, f"Authenticated as {login or 'user'}")


def probe_local_git(
    config: dict,
    *,
    repos_dirs: list[str] | None = None,
) -> ProbeResult:
    """Check that ``git`` can find at least one commit by ``author_email``.

    ``repos_dirs`` is a list of root directories — the probe scans each root
    itself (``git -C <root>``) and, if that fails or yields nothing, walks one
    level deep looking for ``<root>/<repo>/.git``. The first root that yields a
    hit wins; only if every root is empty do we report failure.

    The probe is intentionally read-only: it never mutates config or touches
    the filesystem beyond ``iterdir`` + ``git log`` subprocesses.
    """
    email = (config.get("author_email") or "").strip()
    if not email:
        return ProbeResult(False, "author_email is required")
    if not shutil.which("git"):
        return ProbeResult(False, "`git` binary not found on PATH")
    roots = [Path(d).expanduser() for d in (repos_dirs or [])]
    roots = [r for r in roots if r.exists()]
    if not roots:
        return ProbeResult(False, "repos_dir is not set or does not exist")

    found: list[str] = []
    permission_errors: list[str] = []

    for root in roots:
        # Fast path: the root itself might be a single repo.
        try:
            proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "log",
                    f"--author={email}",
                    "-n",
                    "1",
                    "--all",
                    "--pretty=%h",
                ],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except Exception:
            # ``-C <root>`` will fail if root isn't itself a repo — fall
            # through to the per-subdir scan.
            proc = None  # type: ignore[assignment]

        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            return ProbeResult(True, f"Found commits by {email} in {root}")

        try:
            children = sorted(root.iterdir())
        except PermissionError:
            permission_errors.append(str(root))
            continue
        except OSError:
            # Unreadable root — not fatal, try the next one.
            continue

        for child in children:
            if not (child / ".git").exists():
                continue
            try:
                proc = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(child),
                        "log",
                        f"--author={email}",
                        "-n",
                        "1",
                        "--pretty=%h",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT_SECONDS,
                )
            except Exception:
                continue
            if proc.returncode == 0 and proc.stdout.strip():
                found.append(child.name)
                if len(found) >= 3:
                    return ProbeResult(True, f"Found commits in: {', '.join(found)}")

    if found:
        return ProbeResult(True, f"Found commits in: {', '.join(found)}")
    if permission_errors:
        return ProbeResult(
            False,
            f"Cannot read {', '.join(permission_errors)} — check permissions",
        )
    roots_display = ", ".join(str(r) for r in roots)
    return ProbeResult(False, f"No commits by {email} found in {roots_display}")


_CURSOR_TRANSCRIPT_ROOTS = [
    # macOS
    "~/Library/Application Support/Cursor/User/globalStorage/cursor.cursor",
    "~/Library/Application Support/Cursor/User/workspaceStorage",
    # Linux
    "~/.config/Cursor/User/globalStorage/cursor.cursor",
    "~/.config/Cursor/User/workspaceStorage",
    # Windows
    "~/AppData/Roaming/Cursor/User/globalStorage/cursor.cursor",
    "~/AppData/Roaming/Cursor/User/workspaceStorage",
    # Cross-platform project cache
    "~/.cursor/projects",
]


def probe_cursor(config: dict) -> ProbeResult:  # noqa: ARG001 — symmetric signature
    """Check that Cursor's local data directory exists and is readable."""
    for raw in _CURSOR_TRANSCRIPT_ROOTS:
        path = Path(os.path.expanduser(raw))
        if path.exists():
            return ProbeResult(True, f"Found Cursor data at {path}")
    return ProbeResult(
        False,
        f"No Cursor data found (looked under {platform.system()} default paths)",
    )


PROBES = {
    "jira": probe_jira,
    "confluence": probe_confluence,
    "gitlab": probe_gitlab,
    "github": probe_github,
    "local_git": probe_local_git,
    "cursor": probe_cursor,
}


__all__ = ["PROBES", "ProbeResult"]
