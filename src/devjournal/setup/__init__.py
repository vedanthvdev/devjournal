# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""devjournal setup UI — a tiny local web server for one-click configuration.

The setup package is opt-in: install with ``pip install devjournal[setup]`` to
pull in the keyring backend used for token storage. The server itself uses
only the Python stdlib (``http.server``), binds to ``127.0.0.1`` on a random
port, and enforces a per-session CSRF token plus same-origin checks.

Public entry point::

    from devjournal.setup import run_setup_ui
    run_setup_ui(open_browser=True)
"""

from __future__ import annotations

from devjournal.setup.server import run_setup_ui

__all__ = ["run_setup_ui"]
