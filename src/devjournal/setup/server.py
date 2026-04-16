# SPDX-FileCopyrightText: 2026 Vedanth Vasudev
# SPDX-License-Identifier: MIT
"""HTTP server backing the setup UI.

Uses ``http.server`` so no third-party web framework is pulled in. Security
properties we rely on:

* Bound to ``127.0.0.1`` on a random free port (never a public interface).
  The CLI enforces a loopback-only bind address; ``build_server`` rejects
  anything else to prevent accidental ``0.0.0.0`` exposure.
* Every mutating request must carry ``X-DevJournal-Token`` matching the
  per-session token generated at startup. Comparison uses
  :func:`secrets.compare_digest` to avoid timing leaks.
* ``Origin`` / ``Referer`` are checked on mutating requests: at least one
  must be present *and* match the expected origin. Missing both is treated
  as cross-origin and rejected.
* Strict ``Content-Security-Policy`` on the served HTML and a minimal
  ``default-src 'none'`` on JSON responses.
* The server auto-shuts down after ``IDLE_TIMEOUT_SECONDS`` of no traffic.
* Config writes are atomic (tempfile + ``os.replace``) and the file is
  created with mode ``0o600`` so a concurrent reader never sees plaintext
  secrets with default umask.
"""

from __future__ import annotations

import importlib.resources
import ipaddress
import json
import logging
import mimetypes
import os
import secrets
import tempfile
import threading
import time
import webbrowser
from datetime import date as _date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from devjournal import __version__
from devjournal.config import (
    DEFAULT_CONFIG_PATH,
    get_collector_config,
)
from devjournal.setup.probes import PROBES
from devjournal.setup.secrets import SecretStore

log = logging.getLogger("devjournal")

IDLE_TIMEOUT_SECONDS = 30 * 60
MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB — payloads here are tiny
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class _BadRequest(Exception):
    """Raised by body-parsing helpers to force a 400 or 413 response.

    Using an exception rather than sentinel strings means we can never
    collide with a legitimate JSON payload that happens to equal a
    sentinel value — which is important now that the API accepts
    arbitrary client-supplied objects.
    """

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message

# Collectors whose primary token is redacted on GET /api/config and potentially
# moved into the OS keyring on POST. Confluence shares Atlassian creds with
# Jira so it gets the same treatment.
_SECRET_CONFIG_KEYS: dict[str, str] = {
    "jira": "api_token",
    "confluence": "api_token",
    "gitlab": "token",
    "github": "token",
}
_ASSET_MIMES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}
_STATIC_ALLOWED = {"app.js", "styles.css", "logo.svg"}


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Server state — attached to the handler class, NOT a module global, so tests
# (and any future multi-server setup) don't race.
# ---------------------------------------------------------------------------


class _ServerState:
    """Mutable state shared across handler instances for one server."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.csrf_token = secrets.token_urlsafe(32)
        self.secret_store = SecretStore()
        self.last_activity = time.monotonic()
        self.shutdown_requested = threading.Event()
        self.expected_origin = ""  # filled in when the server starts
        # Lock guards _load → merge → _write round trips so two concurrent
        # saves can't interleave and produce a torn config file.
        self.save_lock = threading.Lock()
        # Separate lock for the "Run now" endpoint. Runs take 30–60 s
        # (multiple network calls across collectors), so we mustn't share
        # ``save_lock`` — a save shouldn't have to wait for a run. We use
        # non-blocking ``acquire`` to answer 409 Conflict instead of
        # queueing, so a double-click doesn't silently spawn two runs.
        self.run_lock = threading.Lock()
        # ``devjournal.setup`` is the Python package; ``assets/`` is a plain
        # folder inside it (no __init__.py), force-included by hatch's build
        # config.
        self.assets_dir = Path(str(importlib.resources.files("devjournal.setup"))) / "assets"

    def touch(self) -> None:
        self.last_activity = time.monotonic()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_raw_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_config()
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _default_config() -> dict[str, Any]:
    return {
        "vault_path": str(Path.home() / "Documents" / "Obsidian Vault"),
        "repos_dir": str(Path.home() / "Code"),
        "collectors": {
            "jira": {"enabled": False, "domain": "", "email": "", "api_token": "", "projects": []},
            "confluence": {"enabled": False},
            "gitlab": {"enabled": False, "url": "https://gitlab.com", "token": "", "username": ""},
            "github": {"enabled": False, "token": "", "username": ""},
            "local_git": {"enabled": True, "author_email": ""},
            "cursor": {"enabled": True},
        },
        "schedule": {"morning": "08:30", "evening": "17:00", "weekdays_only": True},
    }


def _build_secrets_present(config: dict, store: SecretStore) -> dict[str, bool]:
    """For each secret-bearing collector, does a token exist anywhere?"""
    present: dict[str, bool] = {}
    collectors = config.get("collectors", {}) or {}
    for name, yaml_key in _SECRET_CONFIG_KEYS.items():
        # Confluence piggybacks on jira's keyring entry when it has no token of
        # its own — that way "Confluence configured" tracks "Jira configured".
        yaml_value = (collectors.get(name) or {}).get(yaml_key) or ""
        result = store.read(name, yaml_value)
        if not result.value and name == "confluence":
            jira_value = (collectors.get("jira") or {}).get("api_token") or ""
            result = store.read("jira", jira_value)
        present[name] = bool(result.value)
    return present


def _redact_config_for_client(config: dict) -> dict:
    """Strip token values before sending config to the browser."""
    safe = json.loads(json.dumps(config))  # deep copy via JSON
    for name, key in _SECRET_CONFIG_KEYS.items():
        section = safe.get("collectors", {}).get(name)
        if isinstance(section, dict) and section.get(key):
            section[key] = ""
    return safe


def _merge_save_payload(
    existing: dict,
    incoming: dict,
    secrets_payload: dict[str, Any],
    store: SecretStore,
) -> tuple[dict, dict[str, bool], dict[str, str], list[str]]:
    """Merge the browser's edits into the on-disk config + keyring.

    Returns ``(new_config, secrets_present, secrets_backend, write_errors)``.

    * ``secrets_backend`` maps each *changed* secret to ``"keyring"`` or
      ``"yaml"`` so the UI can render a per-collector status banner.
    * ``write_errors`` is a list of collector names whose keyring write
      failed — the UI must warn the user that those tokens ended up in
      ``config.yaml`` in plaintext because the keychain rejected the
      write.
    """
    result = json.loads(json.dumps(existing))  # start from disk state
    for top_level in ("vault_path", "repos_dir"):
        if top_level in incoming:
            result[top_level] = incoming[top_level]

    if "schedule" in incoming and isinstance(incoming["schedule"], dict):
        result.setdefault("schedule", {})
        result["schedule"].update(incoming["schedule"])

    # INVARIANT: we *merge* per-collector rather than replace. The setup UI
    # always renders every collector as a row and therefore always posts
    # every collector in its payload, so this is lossless in normal use.
    # Programmatic callers (tests, hypothetical scripted API users) that
    # send ``collectors: {}`` or an incomplete dict inherit the on-disk or
    # ``_default_config()`` values for omitted keys — crucially,
    # ``_default_config()`` has ``local_git`` and ``cursor`` enabled by
    # default. A caller who intends "no collectors" must therefore send
    # ``{"name": {"enabled": false}}`` explicitly for each one.
    # (Replacing wholesale would be safer for programmatic callers but
    # would break the UI's per-field edit flow, which is the primary
    # consumer of this endpoint.)
    incoming_collectors = incoming.get("collectors", {}) or {}
    result.setdefault("collectors", {})
    for name, section in incoming_collectors.items():
        if not isinstance(section, dict):
            continue
        merged = dict(result["collectors"].get(name, {}) or {})
        merged.update(section)
        result["collectors"][name] = merged

    secrets_backend: dict[str, str] = {}
    write_errors: list[str] = []
    for collector, token in secrets_payload.items():
        if collector not in _SECRET_CONFIG_KEYS:
            log.warning("Ignoring secret for unknown collector %s", collector)
            continue
        yaml_key = _SECRET_CONFIG_KEYS[collector]
        section = result["collectors"].setdefault(collector, {})
        if token in (None, ""):
            # Caller requested we clear the stored secret.
            store.delete(collector)
            section[yaml_key] = ""
            secrets_backend[collector] = "cleared"
            continue
        if not isinstance(token, str):
            continue
        outcome = store.write(collector, token)
        if outcome.backend == "keyring":
            section[yaml_key] = ""  # never keep plaintext in yaml when keyring wins
            secrets_backend[collector] = "keyring"
        else:
            section[yaml_key] = token
            secrets_backend[collector] = "yaml"
            if outcome.error:
                write_errors.append(collector)

    secrets_present = _build_secrets_present(result, store)
    return result, secrets_present, secrets_backend, write_errors


def _write_config(path: Path, config: dict) -> None:
    """Write ``config`` atomically with mode 0o600.

    Uses ``NamedTemporaryFile`` in the same directory + ``os.replace`` so a
    crash mid-write leaves either the old file or the new one — never a
    truncated YAML that breaks ``load_config``. The file is created with
    ``0o600`` via ``os.open`` flags, so there is no window between write
    and chmod during which another local user could read plaintext
    secrets through a leaked umask.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError as exc:
        log.debug("Could not chmod 700 on %s: %s", path.parent, exc)

    content = yaml.safe_dump(config, sort_keys=False).encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(
        prefix=".config.yaml.", suffix=".tmp", dir=str(path.parent)
    )
    # ``fd`` starts out owned by us; once we hand it to ``os.fdopen`` the file
    # object takes ownership and we must not close the raw fd. Tracking that
    # transfer via this sentinel lets the except branch close the fd iff we
    # never got to fdopen (e.g. os.fchmod raised on Windows + Python < 3.13).
    fd_owned = True
    try:
        # fchmod is not available on Windows before CPython 3.13. The final
        # path.chmod(0o600) after os.replace is the cross-platform fallback.
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError) as exc:
            log.debug("os.fchmod unavailable (%s) — will chmod post-replace", exc)
        with os.fdopen(fd, "wb") as f:
            fd_owned = False
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if fd_owned:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Cross-platform belt-and-suspenders: chmod the final path too so the
    # file never sits at umask default on Windows / filesystems where
    # fchmod is a no-op.
    try:
        path.chmod(0o600)
    except OSError as exc:
        log.debug("Could not chmod 600 on %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class SetupHandler(BaseHTTPRequestHandler):
    """Base request handler. Concrete handler classes bind ``state`` per-server."""

    server_version = "devjournal-setup/1.0"
    state: _ServerState  # filled in by ``build_server`` via a subclass

    # ----- logging: keep the dev stdout sane -----

    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug("[setup-ui] " + fmt, *args)

    # ----- security checks -----

    def _same_origin(self) -> bool:
        """Check Origin/Referer on mutating requests. Fails closed when both
        headers are absent — defense-in-depth alongside the CSRF token."""
        origin = self.headers.get("Origin")
        referer = self.headers.get("Referer")
        if not origin and not referer:
            return False
        expected = self.state.expected_origin
        if origin is not None and origin != expected:
            return False
        if referer is not None:
            parsed = urlparse(referer)
            if f"{parsed.scheme}://{parsed.netloc}" != expected:
                return False
        return True

    def _csrf_ok(self) -> bool:
        got = self.headers.get("X-DevJournal-Token", "")
        return secrets.compare_digest(got, self.state.csrf_token)

    # ----- response helpers -----

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(
        self, status: HTTPStatus, body: bytes, content_type: str, *, csp: str | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message})

    # ----- request dispatch -----

    def do_GET(self) -> None:  # noqa: N802 — stdlib API
        self.state.touch()
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/":
            return self._serve_index()
        if route.startswith("/static/"):
            return self._serve_static(route[len("/static/") :])
        if route == "/api/config":
            return self._api_get_config()
        self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown route")

    def do_POST(self) -> None:  # noqa: N802
        self.state.touch()
        if not self._same_origin():
            return self._send_error_json(HTTPStatus.FORBIDDEN, "Cross-origin blocked")
        if not self._csrf_ok():
            return self._send_error_json(HTTPStatus.FORBIDDEN, "CSRF token missing or invalid")

        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/config":
            return self._api_save_config()
        if route.startswith("/api/test/"):
            return self._api_test(route[len("/api/test/") :])
        if route == "/api/schedule":
            return self._api_schedule()
        if route == "/api/run":
            return self._api_run()
        if route == "/api/shutdown":
            return self._api_shutdown()
        self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown route")

    # ----- route handlers -----

    def _serve_index(self) -> None:
        html_path = self.state.assets_dir / "index.html"
        html = html_path.read_text(encoding="utf-8")
        html = html.replace("__CSRF_TOKEN__", self.state.csrf_token)
        csp = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'"
        )
        self._send_bytes(
            HTTPStatus.OK,
            html.encode("utf-8"),
            "text/html; charset=utf-8",
            csp=csp,
        )

    def _serve_static(self, rel: str) -> None:
        if rel not in _STATIC_ALLOWED:
            return self._send_error_json(HTTPStatus.NOT_FOUND, "Not an asset")
        asset_path = self.state.assets_dir / rel
        if not asset_path.exists():
            return self._send_error_json(HTTPStatus.NOT_FOUND, "Missing asset")
        mime = _ASSET_MIMES.get(asset_path.suffix) or mimetypes.guess_type(str(asset_path))[0] \
            or "application/octet-stream"
        self._send_bytes(HTTPStatus.OK, asset_path.read_bytes(), mime)

    def _api_get_config(self) -> None:
        config = _load_raw_config(self.state.config_path)
        secrets_present = _build_secrets_present(config, self.state.secret_store)
        redacted = _redact_config_for_client(config)
        self._send_json(
            HTTPStatus.OK,
            {
                "config": redacted,
                "secrets_present": secrets_present,
                "keyring_available": self.state.secret_store.keyring_available,
                "version": __version__,
            },
        )

    def _read_json_body(self) -> Any:
        """Return the parsed JSON body. Raises :class:`_BadRequest` on
        any protocol error (malformed header, oversize body, invalid
        JSON). Returns ``{}`` for an absent body so callers can treat
        "no body" and "empty object body" identically.
        """
        raw_len = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "Invalid Content-Length") from exc
        if length < 0:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
        if length == 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise _BadRequest(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload too large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "Invalid JSON body") from exc

    def _read_json_dict(self) -> dict[str, Any]:
        """Like :meth:`_read_json_body` but insists the top-level value is
        an object. Lists / strings / numbers / booleans / null are all
        legitimate JSON but never a valid request shape for this API."""
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
        return payload

    def _api_save_config(self) -> None:
        try:
            payload = self._read_json_dict()
        except _BadRequest as exc:
            return self._send_error_json(exc.status, exc.message)
        incoming = payload.get("config") or {}
        if not isinstance(incoming, dict):
            return self._send_error_json(HTTPStatus.BAD_REQUEST, "`config` must be an object")
        secrets_in = payload.get("secrets") or {}
        if not isinstance(secrets_in, dict):
            return self._send_error_json(HTTPStatus.BAD_REQUEST, "`secrets` must be an object")

        state = self.state
        with state.save_lock:
            existing = _load_raw_config(state.config_path)
            merged, secrets_present, secrets_backend, write_errors = _merge_save_payload(
                existing, incoming, secrets_in, state.secret_store,
            )
            try:
                _write_config(state.config_path, merged)
            except OSError as exc:
                return self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    f"Failed to write config: {exc}",
                )

        keyring_used = any(v == "keyring" for v in secrets_backend.values())
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "secrets_present": secrets_present,
                "secrets_backend": secrets_backend,
                "keyring_used": keyring_used,
                "write_errors": write_errors,
            },
        )

    def _api_test(self, collector: str) -> None:
        probe = PROBES.get(collector)
        if probe is None:
            return self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown integration")

        # Accept an optional request body with the user's in-flight form state
        # (POST /api/test/<name>). First-run users haven't saved yet, so the
        # only way to test connectivity is to take the values straight from the
        # form. Disk state is used as the base so existing tokens in the
        # keyring still work when the user only edits non-secret fields.
        try:
            payload = self._read_json_dict()
        except _BadRequest as exc:
            return self._send_error_json(exc.status, exc.message)

        state = self.state
        config = _load_raw_config(state.config_path)

        # Merge the UI's current values on top of disk state.
        overrides = payload.get("collectors") or {}
        if not isinstance(overrides, dict):
            overrides = {}
        if overrides:
            config = json.loads(json.dumps(config))
            config.setdefault("collectors", {})
            for name, fields in overrides.items():
                if not isinstance(fields, dict):
                    continue
                merged = dict(config["collectors"].get(name, {}) or {})
                merged.update(fields)
                config["collectors"][name] = merged
        if payload.get("repos_dir"):
            config["repos_dir"] = payload["repos_dir"]

        # Inline the in-flight secret (never persisted) if the UI sent one.
        inline_secrets = payload.get("secrets") or {}
        if isinstance(inline_secrets, dict):
            for coll, token in inline_secrets.items():
                yaml_key = _SECRET_CONFIG_KEYS.get(coll)
                if yaml_key and isinstance(token, str) and token:
                    config.setdefault("collectors", {}).setdefault(coll, {})
                    config["collectors"][coll][yaml_key] = token

        section = get_collector_config(config, collector)
        yaml_key = _SECRET_CONFIG_KEYS.get(collector)
        if yaml_key is not None and not section.get(yaml_key):
            # Resolve from keychain only if UI didn't provide one.
            resolved = state.secret_store.read(collector, "")
            if resolved.value:
                section[yaml_key] = resolved.value

        if collector == "confluence" and not section.get("api_token"):
            jira_token = (
                (config.get("collectors", {}).get("jira") or {}).get("api_token") or ""
            )
            resolved = state.secret_store.read("jira", jira_token)
            if resolved.value:
                section["api_token"] = resolved.value

        kwargs: dict[str, Any] = {}
        if collector == "local_git":
            kwargs["repos_dir"] = config.get("repos_dir")

        try:
            result = probe(section, **kwargs)
        except Exception:
            log.exception("Probe %s raised", collector)
            return self._send_json(
                HTTPStatus.OK,
                {"ok": False, "detail": "Probe crashed — see server log"},
            )
        self._send_json(HTTPStatus.OK, result.to_dict())

    def _api_schedule(self) -> None:
        try:
            payload = self._read_json_dict()
        except _BadRequest as exc:
            return self._send_error_json(exc.status, exc.message)
        action = payload.get("action")
        if action not in ("install", "remove"):
            return self._send_error_json(
                HTTPStatus.BAD_REQUEST, "`action` must be 'install' or 'remove'"
            )
        state = self.state
        config = _load_raw_config(state.config_path)
        from devjournal.scheduler import install_schedule, remove_schedule
        try:
            if action == "install":
                install_schedule(config)
                message = "Schedule installed."
            else:
                remove_schedule()
                message = "Schedule removed."
        except SystemExit as exc:
            return self._send_json(
                HTTPStatus.OK,
                {"ok": False, "message": f"Scheduling not supported on this OS ({exc})"},
            )
        except Exception:
            log.exception("Schedule action failed")
            return self._send_json(
                HTTPStatus.OK,
                {"ok": False, "message": "Failed to update schedule — see server log"},
            )
        self._send_json(HTTPStatus.OK, {"ok": True, "message": message})

    def _api_run(self) -> None:
        """Trigger a morning/evening collector run for a chosen date.

        Mirrors ``devjournal morning|evening --date <d>`` but runs inline
        so the UI can show a single spinner→banner flow. Serialised via
        a dedicated non-blocking run-lock — a double-click or a second
        tab hitting the same server gets a 409 instead of silently
        spawning a parallel run (which could tear the note file).

        Runs are serialised against *other runs* but **not** against
        saves. That is deliberate: a save shouldn't block a run, and a
        run that started before a save simply reads the pre-save
        config (``os.replace`` is atomic — the read never sees a torn
        file). A user who edits config in one tab and clicks Run in a
        second tab may see the old config apply to that run; they'll
        see the new config on the next run. Accepting that tiny window
        is strictly better than making saves wait for 30–60 s runs.
        """
        try:
            payload = self._read_json_dict()
        except _BadRequest as exc:
            return self._send_error_json(exc.status, exc.message)

        mode = payload.get("mode")
        if mode not in ("morning", "evening"):
            return self._send_error_json(
                HTTPStatus.BAD_REQUEST, "`mode` must be 'morning' or 'evening'"
            )

        raw_date = payload.get("date")
        if not raw_date or not isinstance(raw_date, str):
            return self._send_error_json(
                HTTPStatus.BAD_REQUEST, "`date` is required (YYYY-MM-DD)"
            )
        try:
            target_date = _date.fromisoformat(raw_date)
        except ValueError:
            return self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "`date` must be an ISO-8601 calendar date (YYYY-MM-DD)",
            )

        state = self.state
        if not state.run_lock.acquire(blocking=False):
            return self._send_error_json(
                HTTPStatus.CONFLICT,
                "A run is already in progress — wait for it to finish",
            )
        try:
            self._do_run(state, mode, raw_date, target_date)
        finally:
            state.run_lock.release()

    def _do_run(
        self,
        state: "_ServerState",
        mode: str,
        raw_date: str,
        target_date: _date,
    ) -> None:
        """Load config, construct the engine, and run a single mode.

        Factored out of ``_api_run`` so the outer method only holds
        lifecycle concerns (validation, lock acquire/release). Every
        exit path here writes a JSON response — callers must not
        attempt to send a second one.
        """
        # Imports are deferred so ``import devjournal.setup.server`` stays
        # cheap and so tests can monkeypatch ``load_config`` / ``Engine``.
        # Wrapped in a try because an ImportError here (e.g. a missing
        # optional C extension picked up transitively) would otherwise
        # leak past every other handler and drop the connection.
        try:
            from devjournal.config import load_config
            from devjournal.engine import Engine
        except Exception:
            log.exception("Failed to import engine/config for /api/run")
            return self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Engine import failed — see server log",
            )

        try:
            config = load_config(state.config_path)
        except PermissionError as exc:
            # ``FileNotFoundError`` is normally pre-empted by ``load_config``'s
            # own ``exists()`` check → ``sys.exit(1)`` (caught below), but a
            # TOCTOU race where the file is deleted *after* the check can still
            # surface here. Treat permission issues the same way for
            # consistency.
            return self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                f"Config could not be loaded: {exc}",
            )
        except SystemExit:
            # ``load_config`` calls ``sys.exit(1)`` for *two* distinct
            # user-fixable reasons: the file doesn't exist, or required
            # keys are missing from the parsed YAML. We branch on file
            # existence so the error tells the truth — telling a user
            # "fix your vault_path" when the file has simply been
            # deleted is actively misleading.
            if not state.config_path.exists():
                error = (
                    f"Config file is missing ({state.config_path}). "
                    "Save the Vault section above to create it, then run again."
                )
            else:
                error = (
                    "Config is missing required fields (typically "
                    "vault_path). Fix it in the Vault section above "
                    "and save before running."
                )
            return self._send_json(
                HTTPStatus.OK,
                {"ok": False, "mode": mode, "date": raw_date, "error": error},
            )
        except Exception:
            log.exception("Failed to load config for /api/run")
            return self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Config load failed — see server log",
            )

        # Collector constructors are trivial today, but a future eager-auth
        # collector could raise in ``__init__``. We therefore wrap
        # ``Engine(config)`` in the same ``try`` as the actual run so *no*
        # engine-side exception can escape past the JSON boundary — the
        # client always gets a clean ``ok:false`` banner instead of a
        # torn socket.
        started = time.monotonic()
        try:
            engine = Engine(config)
            if mode == "morning":
                note_path = engine.run_morning(target_date)
            else:
                note_path = engine.run_evening(target_date)
        except KeyError as exc:
            # Missing required config key (e.g. vault_path) — user-fixable.
            return self._send_json(
                HTTPStatus.OK,
                {
                    "ok": False,
                    "mode": mode,
                    "date": raw_date,
                    "error": f"Missing config: {exc}",
                },
            )
        except Exception:
            log.exception("Run failed: mode=%s date=%s", mode, raw_date)
            return self._send_json(
                HTTPStatus.OK,
                {
                    "ok": False,
                    "mode": mode,
                    "date": raw_date,
                    "error": "Run failed — see server log for details",
                },
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "mode": mode,
                "date": raw_date,
                "note_path": str(note_path),
                "note_name": note_path.name,
                "duration_ms": duration_ms,
            },
        )

    def _api_shutdown(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()
        # Request shutdown; ``_idle_watcher`` notices the event on its next tick.
        self.state.shutdown_requested.set()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _idle_watcher(server: ThreadingHTTPServer, state: _ServerState) -> None:
    """Shut the server down after prolonged inactivity or an explicit request.

    Polls every second so explicit shutdowns trigger near-instantly instead
    of waiting for the full idle interval.
    """
    while not state.shutdown_requested.wait(timeout=1.0):
        if time.monotonic() - state.last_activity > IDLE_TIMEOUT_SECONDS:
            log.info("Setup UI idle for %ds — shutting down", IDLE_TIMEOUT_SECONDS)
            state.shutdown_requested.set()
            break
    # ``ThreadingHTTPServer.shutdown()`` must not run on the main request
    # loop; dispatch it in a separate thread.
    threading.Thread(target=server.shutdown, daemon=True).start()


def build_server(
    *,
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    secret_store: SecretStore | None = None,
) -> tuple[ThreadingHTTPServer, _ServerState]:
    """Create a bound, ready-to-serve HTTP server plus its state.

    Rejects non-loopback ``host`` values to prevent accidentally exposing
    tokens on a LAN interface. Split out from :func:`run_setup_ui` so tests
    can drive the lifecycle directly.
    """
    if not _is_loopback(host):
        raise ValueError(
            f"Setup UI may only bind to a loopback address; got {host!r}. "
            "Use 127.0.0.1, localhost, or ::1."
        )

    target_config = config_path or DEFAULT_CONFIG_PATH
    # Create and lock down the directory that will actually hold the config,
    # not a hard-coded default — tests and ``--config`` users supply their
    # own path, and chmodding the wrong directory is both useless to them
    # and an observable side-effect on ~/.config/devjournal we don't want.
    target_config.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_config.parent.chmod(0o700)
    except OSError as exc:  # Windows or unusual filesystems
        log.debug("Could not chmod 700 on %s: %s", target_config.parent, exc)

    state = _ServerState(target_config)
    if secret_store is not None:
        state.secret_store = secret_store

    # Per-server handler subclass so the state is attached to the class
    # rather than a module global — lets tests run multiple servers without
    # racing on shared state.
    bound_state = state

    class BoundHandler(SetupHandler):
        pass

    BoundHandler.state = bound_state  # type: ignore[attr-defined]
    server = ThreadingHTTPServer((host, port), BoundHandler)
    actual_port = server.server_address[1]
    state.expected_origin = f"http://{host}:{actual_port}"
    return server, state


def run_setup_ui(
    *,
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> None:
    """Start the setup UI and block until shutdown."""
    server, state = build_server(config_path=config_path, host=host, port=port)

    url = f"{state.expected_origin}/"
    print(f"devjournal setup UI → {url}")
    print("Press Ctrl-C (or click Done in the browser) to exit.")

    watcher = threading.Thread(
        target=_idle_watcher, args=(server, state), daemon=True
    )
    watcher.start()

    if open_browser:
        try:
            webbrowser.open(url, new=2)
        except Exception as exc:  # pragma: no cover — platform specific
            log.debug("webbrowser.open failed: %s", exc)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log.info("Setup UI interrupted by user")
    finally:
        state.shutdown_requested.set()
        server.server_close()
        print("devjournal setup UI stopped.")


__all__ = [
    "run_setup_ui",
    "build_server",
    "IDLE_TIMEOUT_SECONDS",
    "MAX_BODY_BYTES",
]
