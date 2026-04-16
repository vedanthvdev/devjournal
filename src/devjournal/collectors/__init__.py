# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Collector registry — auto-discovers all Collector subclasses in this package."""

from devjournal.collector import Collector

# Import every collector module so their classes register as Collector subclasses.
from devjournal.collectors import (  # noqa: F401
    confluence,
    cursor,
    github,
    gitlab,
    jira,
    local_git,
)


def get_all_collector_classes() -> list[type[Collector]]:
    """Return every concrete Collector subclass that has been imported."""
    return [cls for cls in Collector.__subclasses__() if not getattr(cls, "_abstract", False)]
