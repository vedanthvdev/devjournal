#!/bin/bash
# Cursor hook: on session end, re-parse today's transcripts so the
# next `devjournal evening` run picks them up.
#
# Install: copy this file to ~/.config/devjournal/hooks/ and make executable.
# Then merge extras/cursor/hooks.json into ~/.cursor/hooks.json.

set -euo pipefail

# Use devjournal's Python environment if installed in a venv
PYTHON="${DEVJOURNAL_PYTHON:-python3}"

$PYTHON -c "
from devjournal.collectors.cursor import CursorCollector
from datetime import date
c = CursorCollector()
# Just triggering the parse — results are used by the next devjournal run.
c.collect(date.today(), {})
" 2>/dev/null || true

exit 0
