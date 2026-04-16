"""Cursor collector — parses AI coding agent sessions from Cursor IDE.

Two data sources:
1. Agent transcripts: ``~/.cursor/projects/*/agent-transcripts/*.jsonl``
   (full agent-mode sessions with tool call history)
2. Cursor state DB: ``~/Library/Application Support/Cursor/User/globalStorage/state.vscdb``
   (all session types including chat/ask/review mode)
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from devjournal.collector import Collector, CollectorResult

log = logging.getLogger("devjournal")

CURSOR_PROJECTS = Path.home() / ".cursor" / "projects"


def _cursor_state_db_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return (
            Path.home() / "Library" / "Application Support" / "Cursor" / "User"
            / "globalStorage" / "state.vscdb"
        )
    if system == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    return Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"

_TOKEN_PATTERN = re.compile(
    r"(glpat-\S+|ATATT\S+|ghp_\S+|gho_\S+|sk-\S+|Bearer\s+\S+|xoxb-\S+|xoxp-\S+)",
    re.IGNORECASE,
)
_TASK_KEYWORDS = re.compile(
    r"(implement|create|build|fix|update|add|run|test|deploy|"
    r"migration|automate|refactor|debug|set up|configure|review)",
    re.IGNORECASE,
)


class CursorCollector(Collector):
    name = "cursor"
    config_key = "cursor"

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        transcript_sessions = self._parse_transcripts(target_date)
        db_sessions = self._parse_state_db(target_date)

        merged = dict(transcript_sessions)
        for sid, ds in db_sessions.items():
            if sid in merged:
                if ds.get("summary") and len(ds["summary"]) > 10:
                    existing = merged[sid]
                    if existing["summary"].startswith("Cursor session") or (
                        len(existing["summary"]) > len(ds["summary"]) + 20
                    ):
                        existing["summary"] = ds["summary"]
                continue
            if ds.get("queries", 0) == 0:
                continue
            merged[sid] = ds

        items = _group_sessions(list(merged.values()))
        return CollectorResult(
            section_id="cursor_sessions",
            heading="### Cursor Sessions",
            items=items,
            empty_message="No Cursor sessions logged today.",
        )

    # ------------------------------------------------------------------
    # Source 1: Agent transcripts (JSONL files)
    # ------------------------------------------------------------------

    def _parse_transcripts(self, target_date: date) -> dict[str, dict]:
        sessions: dict[str, dict] = {}
        if not CURSOR_PROJECTS.is_dir():
            return sessions

        for project_dir in CURSOR_PROJECTS.iterdir():
            if not project_dir.is_dir():
                continue
            transcripts_dir = project_dir / "agent-transcripts"
            if not transcripts_dir.is_dir():
                continue
            project_name = _extract_project_name(project_dir.name)
            for session_dir in transcripts_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                try:
                    mtime = datetime.fromtimestamp(
                        session_dir.stat().st_mtime, tz=timezone.utc
                    ).astimezone().date()
                    if mtime != target_date:
                        continue
                except OSError:
                    continue
                sid = session_dir.name
                jsonl = session_dir / f"{sid}.jsonl"
                if not jsonl.exists():
                    continue
                parsed = _parse_transcript_file(jsonl)
                if parsed:
                    sessions[sid] = {
                        "project": project_name,
                        "summary": parsed["summary"],
                        "files": parsed["files"],
                        "queries": parsed["query_count"],
                        "tool_calls": parsed["tool_call_count"],
                    }
        return sessions

    # ------------------------------------------------------------------
    # Source 2: Cursor state database
    # ------------------------------------------------------------------

    def _parse_state_db(self, target_date: date) -> dict[str, dict]:
        db_path = _cursor_state_db_path()
        if not db_path.exists():
            return {}

        sessions: dict[str, dict] = {}
        db = None
        try:
            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = db.cursor()
            cur.execute("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'")
            for key, val in cur.fetchall():
                if not val or len(val) < 50:
                    continue
                try:
                    data = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    continue

                ts = data.get("lastSendTime", 0) or data.get("createdAt", 0)
                if not ts:
                    continue
                dt = datetime.fromtimestamp(
                    ts / 1000 if ts > 1e12 else ts, tz=timezone.utc
                ).astimezone()
                if dt.date() != target_date:
                    continue

                cid = data.get("composerId", key.replace("composerData:", ""))
                name = data.get("name", "")
                subtitle = data.get("subtitle", "")
                headers = data.get("fullConversationHeadersOnly", [])
                if not headers:
                    continue

                user_bubbles = [h for h in headers if isinstance(h, dict) and h.get("type") == 1]

                # Collect a few user queries for context
                user_queries: list[str] = []
                for h in headers:
                    if not isinstance(h, dict) or h.get("type") != 1:
                        continue
                    bid = h.get("bubbleId", "")
                    if not bid:
                        continue
                    brow = cur.execute(
                        "SELECT value FROM cursorDiskKV WHERE key = ?",
                        (f"bubbleId:{cid}:{bid}",),
                    ).fetchone()
                    if brow and brow[0]:
                        try:
                            text = json.loads(brow[0]).get("text", "").strip()
                            if text and len(text) > 3:
                                user_queries.append(text)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    if len(user_queries) >= 3:
                        break

                summary = name if name and name != "?" else subtitle or ""
                if not summary and user_queries:
                    summary = user_queries[0][:80]
                if not summary:
                    continue
                summary = re.sub(r"\s+", " ", summary).strip()
                if len(summary) > 80:
                    cut = summary[:80].rfind(" ")
                    summary = summary[:cut] + "..." if cut > 20 else summary[:77] + "..."

                files_from_subtitle: list[str] = []
                if subtitle:
                    for prefix in ("Edited ", "Read "):
                        if subtitle.startswith(prefix):
                            files_from_subtitle = [
                                f.strip() for f in subtitle[len(prefix):].split(",") if f.strip()
                            ]
                            break

                sessions[cid] = {
                    "project": _project_from_context(subtitle, user_queries, name),
                    "summary": summary,
                    "files": files_from_subtitle[:10],
                    "queries": len(user_bubbles),
                    "tool_calls": len(headers) - len(user_bubbles),
                }

        except Exception:
            log.debug("Could not read Cursor state DB", exc_info=True)
        finally:
            if db is not None:
                db.close()

        return sessions


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _extract_project_name(project_dir_name: str) -> str:
    """Extract a human-readable project name from Cursor's internal dir name.

    Example: ``Users-alice-Code-myapp-backend`` -> ``backend``
    """
    parts = project_dir_name.split("-")
    # Look for common code-directory markers and take what follows.
    for marker in ("Code", "Projects", "IdeaProjects", "repos", "src"):
        if marker in parts:
            idx = parts.index(marker)
            remainder = parts[idx + 1:]
            if remainder:
                return "-".join(remainder)
    return parts[-1] if parts else project_dir_name


def _project_from_context(
    subtitle: str, queries: list[str], name: str = ""
) -> str:
    """Heuristic: extract a repo/project name from session context."""
    text = " ".join(filter(None, [name, subtitle, *queries[:3]]))
    path_match = re.search(r"/(?:Code|Projects|repos|src)/([^/\s]+)", text)
    if path_match:
        return path_match.group(1).rstrip(".")
    # Look for known repo-name patterns in session name/subtitle.
    repo_match = re.search(
        r"\b([\w]+-[\w]+(?:-[\w]+)*(?:-service|-infra|-api|-lib|-core)?)\b",
        name or subtitle or "",
    )
    if repo_match:
        candidate = repo_match.group(1)
        if len(candidate) > 4 and candidate.lower() not in (
            "two-way", "end-to-end", "update-services",
        ):
            return candidate
    return "Cursor"


def _parse_transcript_file(path: Path) -> dict[str, Any] | None:
    """Parse a single JSONL transcript and extract a summary."""
    user_queries: list[str] = []
    tools_used: dict[str, int] = defaultdict(int)
    files_edited: set[str] = set()

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = entry.get("role", "")
                message = entry.get("message", {})
                if isinstance(message, str):
                    continue
                content_items = message.get("content", [])
                if isinstance(content_items, str):
                    content_items = [{"type": "text", "text": content_items}]

                for item in content_items:
                    if not isinstance(item, dict):
                        continue
                    if role == "user" and item.get("type") == "text":
                        text = item.get("text", "")
                        match = re.search(
                            r"<user_query>\s*(.*?)\s*</user_query>", text, re.DOTALL
                        )
                        if match:
                            q = match.group(1).strip()
                            if q and len(q) > 3:
                                user_queries.append(q)
                    elif item.get("type") == "tool_use":
                        tool_name = item.get("name", "unknown")
                        tools_used[tool_name] += 1
                        inp = item.get("input", {})
                        if isinstance(inp, dict):
                            for key in ("path", "file", "target_notebook"):
                                val = inp.get(key, "")
                                if val and isinstance(val, str) and "/" in val:
                                    basename = os.path.basename(val)
                                    if basename and not basename.startswith("."):
                                        if tool_name in ("Write", "StrReplace", "EditNotebook"):
                                            files_edited.add(basename)
    except Exception:
        return None

    if not user_queries and not tools_used:
        return None

    summary = _pick_summary(user_queries)
    return {
        "summary": summary,
        "files": sorted(files_edited)[:10],
        "query_count": len(user_queries),
        "tool_call_count": sum(tools_used.values()),
    }


def _pick_summary(queries: list[str]) -> str:
    """Choose the most descriptive query as the session summary."""
    for q in queries:
        cleaned = _clean_query(q)
        if cleaned and _TASK_KEYWORDS.search(cleaned):
            return cleaned
    for q in queries:
        cleaned = _clean_query(q)
        if cleaned:
            return cleaned
    return "Cursor session"


def _clean_query(q: str) -> str | None:
    """Sanitise and truncate a user query for display."""
    clean = re.sub(r"\s+", " ", q.replace("\n", " ")).strip()
    clean = _TOKEN_PATTERN.sub("", clean).strip()
    if len(clean) < 10:
        return None
    for sep in (". ", "? ", "! "):
        idx = clean.find(sep)
        if 10 < idx < 80:
            clean = clean[:idx]
            break
    if len(clean) > 80:
        cut = clean[:80].rfind(" ")
        clean = clean[:cut] + "..." if cut > 20 else clean[:77] + "..."
    return clean


def _group_sessions(sessions: list[dict]) -> list[dict]:
    """Merge small sessions that share a project into a single entry.

    Sessions with >3 queries or significant tool usage are kept standalone.
    Small related sessions (reviews, quick checks) are collapsed.
    """
    standalone: list[dict] = []
    buckets: dict[str, list[dict]] = defaultdict(list)

    for session in sessions:
        queries = session.get("queries", 0)
        tools = session.get("tool_calls", 0)
        if queries > 3 or tools > 50:
            standalone.append(session)
        else:
            buckets[session.get("project", "Cursor")].append(session)

    for project, group in buckets.items():
        if len(group) == 1:
            standalone.append(group[0])
            continue
        total_queries = sum(s.get("queries", 0) for s in group)
        total_tools = sum(s.get("tool_calls", 0) for s in group)
        all_files: list[str] = []
        summaries: list[str] = []
        for s in group:
            all_files.extend(s.get("files", []))
            summaries.append(s.get("summary", ""))
        unique_files = sorted(set(all_files))[:10]
        combined_summary = summaries[0] if summaries else "Cursor sessions"
        if len(group) > 1:
            combined_summary += f" (+{len(group) - 1} related sessions)"
        standalone.append({
            "project": project,
            "summary": combined_summary,
            "files": unique_files,
            "queries": total_queries,
            "tool_calls": total_tools,
        })

    return standalone
