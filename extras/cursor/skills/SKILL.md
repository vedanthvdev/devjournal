---
name: devjournal
description: >-
  Update the daily work journal. Use when the user says "update my daily note",
  "what did I do today", "daily summary", "morning agenda", or similar.
---

# devjournal — Daily Note Updater

Update the user's Obsidian daily work journal by running devjournal.

## When to Use

- User asks to update their daily note or journal
- User asks "what did I do today"
- User asks for their morning agenda or what's pending
- End of day and user wants a summary

## Steps

### 1. Determine Mode

- If the user mentions "morning", "agenda", "pending" -> morning mode
- Otherwise -> evening mode (default)

### 2. Run devjournal

```bash
# Evening (default):
devjournal evening

# Morning:
devjournal morning

# Specific date:
devjournal run --date YYYY-MM-DD
```

### 3. Report Back

After running, read the updated daily note and summarise what was added:
- How many Jira tickets
- How many code commits
- Confluence pages
- Cursor sessions logged

The note path is: `<vault_path>/Journal/Daily/YYYY-MM-DD.md`
(vault_path is set in `~/.config/devjournal/config.yaml`)
