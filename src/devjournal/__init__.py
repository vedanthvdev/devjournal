# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""devjournal — Automated daily work journals for engineers."""

from __future__ import annotations

import re
from importlib.metadata import version, PackageNotFoundError


def _format_version(raw: str) -> str:
    """Normalize version for display: ``X.Y.Z.devN`` → ``X.Y.Z-alpha``."""
    return re.sub(r"\.dev\d+$", "-alpha", raw)


try:
    __version__ = _format_version(version("devjournal"))
except PackageNotFoundError:
    try:
        from devjournal._version import __version__ as _raw  # type: ignore[import-not-found]

        __version__ = _format_version(_raw)
    except ImportError:
        __version__ = "0.0.0-alpha"
