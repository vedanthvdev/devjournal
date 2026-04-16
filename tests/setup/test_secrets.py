"""Tests for devjournal.setup.secrets.

We inject an in-memory fake backend so tests don't touch the real OS keychain.
"""

from __future__ import annotations

from devjournal.setup.secrets import SERVICE_NAME, SecretStore


class FakeKeyring:
    """Minimal keyring stand-in. Supports the three methods SecretStore calls."""

    priority = 5.0

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


def test_reads_from_keyring_when_available():
    backend = FakeKeyring()
    backend.set_password(SERVICE_NAME, "jira", "secret-token")
    store = SecretStore(backend=backend)
    result = store.read("jira", yaml_value="fallback")
    assert result.value == "secret-token"
    assert result.source == "keyring"


def test_falls_back_to_yaml_when_keyring_empty():
    store = SecretStore(backend=FakeKeyring())
    result = store.read("gitlab", yaml_value="yaml-token")
    assert result.value == "yaml-token"
    assert result.source == "yaml"


def test_missing_when_neither_source_has_a_value():
    store = SecretStore(backend=FakeKeyring())
    result = store.read("github", yaml_value=None)
    assert result.value == ""
    assert result.source == "missing"


def test_write_returns_keyring_when_backend_available():
    backend = FakeKeyring()
    store = SecretStore(backend=backend)
    result = store.write("jira", "new-token")
    assert result.backend == "keyring"
    assert result.error is None
    assert backend.get_password(SERVICE_NAME, "jira") == "new-token"


def test_write_falls_back_to_yaml_without_backend():
    store = SecretStore(backend=None)
    # Force _backend_checked so _load_keyring is not re-invoked; mark unchecked and
    # simulate the "no backend" path by stubbing _load_keyring.
    store._backend_checked = True  # noqa: SLF001 — targeted test internal access
    store._backend = None  # noqa: SLF001
    result = store.write("jira", "new-token")
    assert result.backend == "yaml"
    assert result.error is None


def test_write_surfaces_backend_error_when_keyring_rejects():
    """Regression for I3: a keyring write failure must not be silently
    downgraded to 'yaml' — callers need to know the user's keychain
    rejected the write so they can warn that the token is now in
    config.yaml in plaintext."""

    class RejectingBackend(FakeKeyring):
        def set_password(self, service: str, username: str, password: str) -> None:
            raise RuntimeError("User clicked Always Deny")

    store = SecretStore(backend=RejectingBackend())
    result = store.write("jira", "new-token")
    assert result.backend == "yaml"
    assert result.error is not None
    assert "Always Deny" in result.error


def test_delete_is_best_effort_and_never_raises():
    class ExplodingBackend(FakeKeyring):
        def delete_password(self, service: str, username: str) -> None:
            raise RuntimeError("boom")

    store = SecretStore(backend=ExplodingBackend())
    store.delete("jira")  # must not raise


def test_roundtrip_read_after_write():
    backend = FakeKeyring()
    store = SecretStore(backend=backend)
    result = store.write("github", "ghp_abc")
    assert result.backend == "keyring"
    assert store.read("github", yaml_value=None).value == "ghp_abc"
    assert store.read("github", yaml_value=None).source == "keyring"


def test_keyring_available_reflects_backend():
    assert SecretStore(backend=FakeKeyring()).keyring_available is True
    empty = SecretStore(backend=None)
    empty._backend_checked = True  # noqa: SLF001
    empty._backend = None  # noqa: SLF001
    assert empty.keyring_available is False
