# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Markdown formatter — turns CollectorResult data into Obsidian-compatible sections.

Each collector stores items in its own dict shape. The formatter dispatches to
a per-section rendering function based on ``section_id``. Unknown section IDs
fall back to a generic bullet-list renderer.
"""

from __future__ import annotations

from collections.abc import Callable

from devjournal.collector import CollectorResult


def format_result(result: CollectorResult) -> str:
    """Render a CollectorResult into a markdown string (including its heading)."""
    renderer = _RENDERERS.get(result.section_id, _render_generic)
    return renderer(result)


def format_carry_forward(items: list[str]) -> str:
    """Render carry-forward items for the morning agenda."""
    heading = "### Carried Forward from Yesterday"
    if not items:
        return f"{heading}\n*Nothing carried forward.*\n"
    lines = [heading] + items
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Per-section renderers
# ---------------------------------------------------------------------------


def _render_jira_active(result: CollectorResult) -> str:
    lines = [result.heading]
    if not result.items:
        lines.append(f"*{result.empty_message}*")
        return "\n".join(lines) + "\n"
    for t in result.items:
        lines.append(f'- [{t["key"]}]({t["link"]}) - {t["summary"]} — **{t["status"]}**')
    return "\n".join(lines) + "\n"


def _render_jira_activity(result: CollectorResult) -> str:
    return _render_jira_active(result)


def _render_code_changes(result: CollectorResult) -> str:
    lines = [result.heading]
    if not result.items:
        lines.append(f"*{result.empty_message}*")
        return "\n".join(lines) + "\n"

    pushes = [i for i in result.items if i.get("type") in ("commit", "push")]
    mrs = [i for i in result.items if i.get("type") in ("mr", "pr")]
    comments = [i for i in result.items if i.get("type") == "comment"]

    # Group commits/pushes by project
    projects: dict[str, list[str]] = {}
    for item in pushes:
        proj = item.get("project", "unknown")
        projects.setdefault(proj, [])
        msg = item.get("message", "")
        if msg and msg not in projects[proj]:
            projects[proj].append(msg)

    for proj, msgs in sorted(projects.items()):
        count = len(msgs)
        lines.append(f"- **{proj}**: {count} commit{'s' if count != 1 else ''}")
        for msg in msgs[:10]:
            lines.append(f"  - {msg}")

    if mrs:
        lines += ["", "**Merge / Pull Requests:**"]
        for item in mrs:
            proj = item.get("project", "")
            prefix = f"**{proj}**: " if proj else ""
            lines.append(f'- {prefix}{item.get("action", "")}: {item.get("title", "")}')

    if comments:
        lines += ["", "**Comments:**"]
        for item in comments:
            proj = item.get("project", "")
            prefix = f"**{proj}**: " if proj else ""
            lines.append(f'- {prefix}{item.get("title", "comment")}')

    return "\n".join(lines) + "\n"


def _render_confluence(result: CollectorResult) -> str:
    lines = [result.heading]
    if not result.items:
        lines.append(f"*{result.empty_message}*")
        return "\n".join(lines) + "\n"
    for p in result.items:
        if p.get("link"):
            lines.append(f'- [{p["title"]}]({p["link"]})')
        else:
            lines.append(f'- {p["title"]}')
    return "\n".join(lines) + "\n"


def _render_cursor_sessions(result: CollectorResult) -> str:
    lines = [result.heading]
    if not result.items:
        lines.append(f"*{result.empty_message}*")
        return "\n".join(lines) + "\n"
    for s in result.items:
        summary = s.get("summary", "Session")
        project = s.get("project", "")
        files = s.get("files", [])
        queries = s.get("queries", 0)
        tool_calls = s.get("tool_calls", 0)
        prefix = f"**{project}**: " if project else ""
        stats = f" ({queries} queries, {tool_calls} tool calls)" if queries else ""
        lines.append(f"- {prefix}{summary}{stats}")
        for fname in files[:8]:
            lines.append(f"  - `{fname}`")
    return "\n".join(lines) + "\n"


def _render_generic(result: CollectorResult) -> str:
    """Fallback renderer for unknown section types."""
    lines = [result.heading]
    if not result.items:
        lines.append(f"*{result.empty_message}*")
        return "\n".join(lines) + "\n"
    for item in result.items:
        label = item.get("title") or item.get("summary") or str(item)
        link = item.get("link")
        if link:
            lines.append(f"- [{label}]({link})")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines) + "\n"


_RENDERERS: dict[str, Callable[[CollectorResult], str]] = {
    "jira_active": _render_jira_active,
    "jira_activity": _render_jira_activity,
    "code_changes": _render_code_changes,
    "confluence": _render_confluence,
    "cursor_sessions": _render_cursor_sessions,
}
