"""Base collector interface and result type.

Every integration (Jira, GitLab, GitHub, etc.) implements the ``Collector``
abstract class. The engine discovers enabled collectors at runtime and calls
``collect`` / ``collect_agenda`` — collectors never know about each other.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class CollectorResult:
    """Uniform structure returned by every collector.

    Attributes:
        section_id: Unique key used for the HTML-comment markers in the note
                    (e.g. ``"jira_activity"``).
        heading: Markdown heading rendered in the note (e.g. ``"### Jira Activity"``).
        items: Arbitrary list of dicts — the formatter knows how to render each
               collector's item shape.
        empty_message: Shown when ``items`` is empty.
    """

    section_id: str
    heading: str
    items: list[dict] = field(default_factory=list)
    empty_message: str = "No activity."


class Collector(ABC):
    """Abstract base for all data-source collectors.

    Subclass this, set ``name`` and ``config_key``, and implement the two
    collection methods. The engine handles everything else.
    """

    name: str = ""
    config_key: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "__abstractmethods__", None):
            if not cls.name or not cls.config_key:
                raise TypeError(
                    f"Collector subclass {cls.__name__} must set 'name' and 'config_key'"
                )

    @abstractmethod
    def collect(self, target_date: date, config: dict) -> CollectorResult:
        """Gather the day's work-log data (evening mode)."""

    def collect_agenda(self, target_date: date, config: dict) -> CollectorResult | None:
        """Gather morning-agenda data. Return ``None`` if not applicable."""
        return None
