"""devjournal — Automated daily work journals for engineers."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("devjournal")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
