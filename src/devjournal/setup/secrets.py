# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""Secret storage — keyring when available, transparent yaml fallback otherwise.

The setup UI prefers the OS keychain (macOS Keychain, freedesktop Secret
Service, Windows Credential Locker) so tokens never sit in plaintext on disk.
When a working keyring backend is not available — headless Linux, CI, etc. —
we fall back to leaving the token in ``config.yaml`` (the existing behaviour)
so nothing breaks.

All secret I/O goes through :class:`SecretStore`. The store is intentionally
stateless; callers hand it the collector name and the store knows how to route
reads and writes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger("devjournal")

SERVICE_NAME = "devjournal"


class _KeyringLike(Protocol):
    """Subset of the keyring API we rely on — lets us inject fakes in tests."""

    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def _load_keyring() -> _KeyringLike | None:
    """Return a usable keyring backend, or ``None`` if keyring is unavailable.

    We treat a ``fail.Keyring`` / ``null.Keyring`` backend as unavailable —
    those are keyring's sentinels for "no real backend found" and silently
    discard writes, which would be worse than an honest fallback.
    """
    try:
        import keyring
        from keyring.backends import fail as _fail
    except ImportError:
        log.debug("keyring not installed — secrets will live in config.yaml")
        return None

    try:
        backend = keyring.get_keyring()
    except Exception as exc:
        log.warning("keyring backend lookup failed (%s) — falling back to yaml", exc)
        return None

    if isinstance(backend, _fail.Keyring):
        log.warning(
            "No usable keyring backend detected — falling back to yaml. "
            "Install `python3-keyring`/`gnome-keyring` or similar for secure storage."
        )
        return None

    # chainer / null backends expose priority <= 0
    priority = float(getattr(backend, "priority", 0) or 0)
    if priority <= 0:
        log.warning(
            "Keyring backend %s has non-positive priority — falling back to yaml.",
            type(backend).__name__,
        )
        return None

    return backend


@dataclass(frozen=True)
class SecretResult:
    """Outcome of a secret read."""

    value: str
    source: str  # "keyring" | "yaml" | "missing"


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a secret write.

    ``backend`` is the storage the caller should treat the value as living
    in: ``"keyring"`` (stored securely), ``"yaml"`` (caller must keep it
    in ``config.yaml``). ``error`` is populated iff the keyring backend
    existed but rejected the write — callers can surface this to the user
    so they know a keychain prompt was denied vs. never existed.
    """

    backend: str
    error: str | None = None


class SecretStore:
    """Route secret reads/writes to the keyring, falling back to the config dict."""

    def __init__(self, backend: _KeyringLike | None = None) -> None:
        # ``backend`` is injectable for testing; production callers pass ``None``
        # and we discover keyring lazily on first use.
        self._backend = backend
        self._backend_checked = backend is not None

    # ------------------------------------------------------------------
    # Backend access
    # ------------------------------------------------------------------

    def _get_backend(self) -> _KeyringLike | None:
        if not self._backend_checked:
            self._backend = _load_keyring()
            self._backend_checked = True
        return self._backend

    @property
    def keyring_available(self) -> bool:
        return self._get_backend() is not None

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------

    def read(self, collector: str, yaml_value: str | None) -> SecretResult:
        """Resolve a secret for ``collector``.

        Order of precedence:

        1. OS keyring (if available and entry exists).
        2. ``yaml_value`` (legacy / fallback).
        3. Empty string with ``source="missing"``.
        """
        backend = self._get_backend()
        if backend is not None:
            try:
                stored = backend.get_password(SERVICE_NAME, collector)
            except Exception as exc:
                log.warning("Keyring read failed for %s: %s", collector, exc)
                stored = None
            if stored:
                return SecretResult(value=stored, source="keyring")

        if yaml_value:
            return SecretResult(value=yaml_value, source="yaml")

        return SecretResult(value="", source="missing")

    def write(self, collector: str, value: str) -> WriteResult:
        """Persist a secret.

        Returns a :class:`WriteResult` so callers can tell whether the
        value ended up in the keyring or had to fall back to yaml, and —
        importantly — whether the fallback was because there was no
        backend at all or because the keyring actively rejected the write
        (e.g. macOS Keychain "Always Deny"). The latter is a user-visible
        event and should surface in the UI, not a silent plaintext-on-disk
        downgrade.
        """
        backend = self._get_backend()
        if backend is None:
            return WriteResult(backend="yaml")
        try:
            backend.set_password(SERVICE_NAME, collector, value)
            return WriteResult(backend="keyring")
        except Exception as exc:
            log.warning("Keyring write failed for %s (%s) — using yaml", collector, exc)
            return WriteResult(backend="yaml", error=str(exc))

    def delete(self, collector: str) -> None:
        """Best-effort removal of a stored secret — never raises."""
        backend = self._get_backend()
        if backend is None:
            return
        try:
            backend.delete_password(SERVICE_NAME, collector)
        except Exception as exc:
            log.debug("Keyring delete for %s: %s", collector, exc)


__all__ = ["SecretStore", "SecretResult", "WriteResult", "SERVICE_NAME"]
