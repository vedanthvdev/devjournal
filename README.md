# devjournal

Automated daily work journals for engineers. Pulls from Jira, GitLab, GitHub, Confluence, Cursor, and local git into your Obsidian vault.

**Morning:** see your agenda, active tickets, and carry-forward tasks.
**Evening:** get an auto-generated summary of everything you did today.

```
devjournal morning   # populate today's agenda
devjournal evening   # populate today's work log
```

## Quick Start

```bash
pip install devjournal
devjournal init          # creates ~/.config/devjournal/config.yaml
```

Edit the config with your API tokens, then:

```bash
devjournal evening       # run it once to see it work
devjournal schedule install  # set up automatic daily runs
```

## How It Works

devjournal collects your daily activity from multiple sources and writes it into a structured Obsidian daily note:

```
Journal/Daily/2026-04-15.md
├── Agenda
│   ├── Jira Tickets (Active)      ← from Jira API
│   ├── Carried Forward             ← from yesterday's note
│   └── Today's Focus               ← you fill this in
├── Work Log
│   ├── Code Changes                ← from GitLab/GitHub + local git
│   ├── Jira Activity               ← tickets you touched today
│   ├── Confluence                   ← pages you edited
│   ├── Cursor Sessions              ← AI coding sessions
│   └── Manual Notes                 ← you add anything else
└── End of Day
    ├── Completed Today              ← you check things off
    └── Carry Forward                ← rolls into tomorrow
```

Each section is updated idempotently using HTML comment markers — you can run it multiple times safely, and your manual notes are never overwritten.

## Configuration

The config file lives at `~/.config/devjournal/config.yaml`. Here's the full reference:

```yaml
vault_path: ~/Documents/Obsidian Vault    # path to your Obsidian vault
repos_dir: ~/Code                          # parent dir of your git repos

collectors:
  jira:
    enabled: true
    domain: yourcompany.atlassian.net
    email: you@company.com
    api_token: ""                          # Atlassian API token
    projects: [PROJ1, PROJ2]               # Jira project keys to track

  confluence:
    enabled: true                          # shares auth with Jira

  gitlab:
    enabled: false
    url: https://gitlab.com                # or your self-hosted instance
    token: ""                              # PAT with read_api scope
    username: your-username

  github:
    enabled: false
    token: ""                              # PAT with repo scope
    username: your-username

  local_git:
    enabled: true
    author_email: you@company.com

  cursor:
    enabled: true                          # no token needed

schedule:
  morning: "08:30"
  evening: "17:00"
  weekdays_only: true
```

Enable only what you use. Each collector runs independently — if one fails, the rest still work.

## Integrations

### Jira

Tracks tickets assigned to you and tickets you've touched today.

1. Go to [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create a token
3. Set `domain`, `email`, `api_token`, and `projects` in your config

### Confluence

Finds pages you created or edited today. Shares authentication with Jira — no extra token needed.

### GitLab

Captures push events, merge requests, and comments.

1. Go to your GitLab instance → Settings → Access Tokens
2. Create a PAT with `read_api` scope
3. Set `url`, `token`, and `username` in your config

Works with gitlab.com and self-hosted instances.

### GitHub

Captures push events, pull requests, reviews, and comments.

1. Go to [GitHub tokens](https://github.com/settings/tokens)
2. Create a classic PAT with `repo` and `read:user` scopes
3. Set `token` and `username` in your config

### Local Git

Scans all repositories under `repos_dir` for commits matching your `author_email`. No API token needed.

### Cursor IDE

Parses Cursor agent transcripts and session data from the local state database. Captures all session types: agent mode, chat, ask, and code review.

No token needed — reads local files only.

## Scheduling

Set up automatic runs so your journal updates itself:

```bash
devjournal schedule install   # installs morning + evening schedule
devjournal schedule remove    # removes it
```

- **macOS**: creates launchd agents (runs even when Terminal is closed)
- **Linux**: adds cron entries

## Cursor Integration

For richer Cursor session tracking, you can install a hook that triggers when sessions end:

1. Copy `extras/cursor/hooks.json` into your `~/.cursor/hooks.json` (merge if one exists)
2. Copy `extras/cursor/hooks/log-session-end.sh` to `~/.config/devjournal/hooks/`
3. Make it executable: `chmod +x ~/.config/devjournal/hooks/log-session-end.sh`

There's also a Cursor skill in `extras/cursor/skills/SKILL.md` — copy it to `~/.cursor/skills/devjournal/` so you can say "update my daily note" in any Cursor session.

## CLI Reference

```
devjournal morning              # populate morning agenda
devjournal evening              # populate evening work log
devjournal run                  # alias for evening
devjournal run --morning        # alias for morning
devjournal run --date 2026-04-14  # run for a specific date
devjournal init                 # create config file
devjournal schedule install     # install automatic scheduling
devjournal schedule remove      # remove scheduling
devjournal --version            # show version
devjournal --verbose evening    # enable debug logging
devjournal -c /path/to/config.yaml evening  # use custom config
```

## Adding a New Collector

See [CONTRIBUTING.md](CONTRIBUTING.md) for a step-by-step guide.

The short version: create a new file in `src/devjournal/collectors/`, subclass `Collector`, implement `collect()`, and add your import to `collectors/__init__.py`. The engine discovers it automatically.

## Development

```bash
git clone https://github.com/vedanthvdev/devjournal.git
cd devjournal
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # run tests
ruff check src/ tests/    # lint
```

## License

MIT
