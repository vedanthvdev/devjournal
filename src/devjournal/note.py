"""Daily note file operations.

Handles creating notes from templates and performing idempotent section
updates using HTML-comment markers (``<!-- BEGIN:id -->`` / ``<!-- END:id -->``).
"""

from __future__ import annotations

import importlib.resources
import logging
import re
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger("devjournal")


def ensure_daily_note(vault_path: str, target_date: date) -> Path:
    """Ensure the daily note exists, creating from the bundled template if needed.

    Returns:
        Path to the daily note file.
    """
    vault = Path(vault_path)
    note_path = vault / "Journal" / "Daily" / f"{target_date.isoformat()}.md"

    if note_path.exists():
        return note_path

    template_text = _load_template("daily.md")
    content = re.sub(
        r"(tags:\s*\n\s*-\s*daily_note)",
        rf"\1\njournal: Daily\njournal-date: {target_date.isoformat()}",
        template_text,
        count=1,
    )

    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content)
    log.info("Created daily note: %s", note_path)
    return note_path


def update_section(content: str, section_id: str, new_content: str) -> str:
    """Replace content between ``<!-- BEGIN:id -->`` and ``<!-- END:id -->`` markers.

    If the markers don't exist (e.g. a note created before this tool was set up),
    the section is appended before the last ``---`` separator.
    """
    begin = f"<!-- BEGIN:{section_id} -->"
    end = f"<!-- END:{section_id} -->"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{begin}\n{new_content}\n{end}"

    if pattern.search(content):
        return pattern.sub(replacement, content)

    block = f"\n{replacement}\n"
    last_hr = content.rfind("\n---")
    if last_hr > 0:
        return content[:last_hr] + block + content[last_hr:]
    return content + block


def get_carry_forward(vault_path: str, target_date: date) -> list[str]:
    """Read unchecked carry-forward items from the most recent previous note."""
    vault = Path(vault_path)

    for days_back in range(1, 8):
        check_date = target_date - timedelta(days=days_back)
        note_path = vault / "Journal" / "Daily" / f"{check_date.isoformat()}.md"
        if not note_path.exists():
            continue
        content = note_path.read_text()
        items: list[str] = []
        in_carry = False
        for line in content.splitlines():
            if "### Carry Forward" in line:
                in_carry = True
                continue
            if in_carry:
                if line.startswith("---") or (line.startswith("#") and "Carry Forward" not in line):
                    break
                stripped = line.strip()
                if stripped.startswith("- [ ]") and stripped[5:].strip():
                    items.append(line.rstrip())
        if items:
            return items
    return []


def _load_template(name: str) -> str:
    """Load a template from the package's ``templates/`` directory."""
    templates = importlib.resources.files("devjournal") / "templates"
    return (templates / name).read_text(encoding="utf-8")
