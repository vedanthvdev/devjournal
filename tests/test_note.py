"""Tests for note file operations (section updates, carry-forward)."""

from __future__ import annotations

from datetime import date

from devjournal.note import ensure_daily_note, get_carry_forward, update_section


def test_update_section_with_markers():
    content = (
        "# Note\n"
        "<!-- BEGIN:test -->\n"
        "old content\n"
        "<!-- END:test -->\n"
        "footer\n"
    )
    result = update_section(content, "test", "new content")
    assert "new content" in result
    assert "old content" not in result
    assert "footer" in result


def test_update_section_idempotent():
    content = "<!-- BEGIN:x -->\nA\n<!-- END:x -->"
    first = update_section(content, "x", "B")
    second = update_section(first, "x", "B")
    assert first == second


def test_update_section_without_markers():
    content = "# Note\nsome text\n---\nfooter"
    result = update_section(content, "new_section", "injected")
    assert "<!-- BEGIN:new_section -->" in result
    assert "injected" in result
    assert result.index("injected") < result.rfind("---")


def test_update_section_no_hr():
    content = "# Note\nsome text"
    result = update_section(content, "x", "data")
    assert "<!-- BEGIN:x -->" in result
    assert "data" in result


def test_ensure_daily_note_creates_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Journal" / "Daily").mkdir(parents=True)

    target = date(2026, 4, 15)
    note_path = ensure_daily_note(str(vault), target)
    assert note_path.exists()
    content = note_path.read_text()
    assert "daily_note" in content
    assert "2026-04-15" in content


def test_ensure_daily_note_existing(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    note = vault / "Journal" / "Daily" / "2026-04-15.md"
    note.write_text("existing")
    result = ensure_daily_note(str(vault), date(2026, 4, 15))
    assert result.read_text() == "existing"


def test_get_carry_forward(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    yesterday_note = vault / "Journal" / "Daily" / "2026-04-14.md"
    yesterday_note.write_text(
        "### Carry Forward\n"
        "- [ ] Finish code review\n"
        "- [x] Done task\n"
        "- [ ] Deploy fix\n"
        "---\n"
    )
    items = get_carry_forward(str(vault), date(2026, 4, 15))
    assert len(items) == 2
    assert "Finish code review" in items[0]
    assert "Deploy fix" in items[1]


def test_get_carry_forward_no_previous(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Journal" / "Daily").mkdir(parents=True)
    items = get_carry_forward(str(vault), date(2026, 4, 15))
    assert items == []
