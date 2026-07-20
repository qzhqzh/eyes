"""Reusable node-side state and HTTP client primitives for Eyes Hub."""

from __future__ import annotations

import json
import os
import random
import secrets
import ssl
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_STATE_DIR = Path("/var/lib/eyes")
DEFAULT_STATE_FILE = "node.json"
PROTOCOL_VERSION = "eyes.node.v1"


class NodeStateError(RuntimeError):
    """Raised when persisted node state is missing required or valid data."""


class HubClientError(RuntimeError):
    """Base error for Hub client failures."""


class HubHTTPError(HubClientError):
    """Raised when the Hub returns a non-success HTTP response."""

    def __init__(self, status_code: int, body: str, reason: str | None = None):
        self.status_code = status_code
        self.body = body
        message = f"Hub returned HTTP {status_code}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class HubTransportError(HubClientError):
    """Raised when a request cannot reach the Hub."""


class HubProtocolError(HubClientError):
    """Raised when the Hub response is not valid JSON."""


@dataclass(frozen=True)
class NodeIdentity:
    """Persistent node identity and optional Hub-issued bearer credential."""

    node_id: str
    credential: str | None = None
    enrolled: bool = False


class NodeStateStore:
    """Persist node identity in a private, atomically replaced JSON file."""

    def __init__(
        self,
        state_dir: str | os.PathLike[str] = DEFAULT_STATE_DIR,
        filename: str = DEFAULT_STATE_FILE,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / filename

    def load(self) -> NodeIdentity | None:
        """Load the persisted identity, returning ``None`` before first use."""
        try:
            with self.path.open("r", encoding="utf-8") as state_file:
                raw = json.load(state_file)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise NodeStateError(f"cannot read node state {self.path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise NodeStateError(f"node state {self.path} must be a JSON object")

        node_id = raw.get("node_id")
        credential = raw.get("credential")
        enrolled = raw.get("enrolled", bool(credential))
        if not isinstance(node_id, str) or not node_id.strip():
            raise NodeStateError(f"node state {self.path} has an invalid node_id")
        if credential is not None and (
            not isinstance(credential, str) or not credential.strip()
        ):
            raise NodeStateError(f"node state {self.path} has an invalid credential")
        if not isinstance(enrolled, bool):
            raise NodeStateError(f"node state {self.path} has an invalid enrolled flag")
        if enrolled and not credential:
            raise NodeStateError(f"node state {self.path} is enrolled without a credential")

        return NodeIdentity(node_id=node_id, credential=credential, enrolled=enrolled)

    def load_or_create(self) -> NodeIdentity:
        """Return stable local identity, creating a UUID on first use."""
        identity = self.load()
        if identity is not None:
            return identity

        identity = NodeIdentity(node_id=str(uuid.uuid4()))
        self.save(identity)
        return identity

    def save(self, identity: NodeIdentity) -> None:
        """Atomically persist an identity with mode ``0600``."""
        if not identity.node_id.strip():
            raise NodeStateError("node_id must not be empty")
        if identity.credential is not None and not identity.credential.strip():
            raise NodeStateError("credential must not be empty")

        try:
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            payload = {
                "node_id": identity.node_id,
                "credential": identity.credential,
                "enrolled": identity.enrolled,
            }
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.state_dir,
            )
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
                    descriptor = -1
                    json.dump(payload, state_file, ensure_ascii=False, sort_keys=True)
                    state_file.write("\n")
                    state_file.flush()
                    os.fsync(state_file.fileno())
                os.replace(temporary_name, self.path)
                os.chmod(self.path, 0o600)
            except Exception:
                if descriptor >= 0:
                    os.close(descriptor)
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise
        except (OSError, TypeError, ValueError) as exc:
            raise NodeStateError(f"cannot write node state {self.path}: {exc}") from exc

    def set_credential(self, credential: str) -> NodeIdentity:
        """Attach a Hub-issued credential to the existing local identity."""
        if not credential.strip():
            raise NodeStateError("credential must not be empty")
        identity = self.load_or_create()
        enrolled = NodeIdentity(
            node_id=identity.node_id,
            credential=credential,
            enrolled=True,
        )
        self.save(enrolled)
        return enrolled

    def prepare_enrollment(self) -> NodeIdentity:
        """Persist a retry-safe node credential before contacting the Hub."""
        identity = self.load_or_create()
        if identity.credential:
            return identity
        pending = NodeIdentity(
            node_id=identity.node_id,
            credential=secrets.token_urlsafe(32),
            enrolled=False,
        )
        self.save(pending)
        return pending

    def mark_enrolled(self) -> NodeIdentity:
        """Mark a previously prepared credential as accepted by the Hub."""
        identity = self.load_or_create()
        if not identity.credential:
            raise NodeStateError("cannot mark enrollment without a credential")
        enrolled = NodeIdentity(
            node_id=identity.node_id,
            credential=identity.credential,
            enrolled=True,
        )
        self.save(enrolled)
        return enrolled


class HubClient:
    """Small synchronous JSON client for the Eyes node protocol."""

    def __init__(
        self,
        base_url: str,
        credential: str | None = None,
        *,
        node_id: str | None = None,
        timeout: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
        user_agent: str = "eyes-node-client/0.1",
        allow_insecure_http: bool = False,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        parsed_url = urlparse(base_url)
        local_hosts = {"127.0.0.1", "::1", "localhost"}
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if (
            parsed_url.scheme == "http"
            and parsed_url.hostname not in local_hosts
            and not allow_insecure_http
        ):
            raise ValueError(
                "remote Hub must use HTTPS; pass allow_insecure_http only for a trusted test network"
            )
        self.base_url = base_url.rstrip("/")
        self.credential = credential
        self.node_id = node_id
        self.timeout = timeout
        self.ssl_context = ssl_context
        self.user_agent = user_agent

    def enroll(
        self,
        token: str,
        node_id: str,
        *,
        node_token: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Exchange a one-time token for Hub enrollment data."""
        if not token:
            raise ValueError("token must not be empty")
        if not node_id:
            raise ValueError("node_id must not be empty")
        payload: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "node_id": node_id,
        }
        if node_token:
            payload["node_token"] = node_token
        if metadata is not None:
            payload.update(
                {
                    key: value
                    for key, value in metadata.items()
                    if key not in {"node_id", "protocol_version"}
                }
            )
        return self._request_json(
            "POST",
            "/api/v1/enroll",
            payload=payload,
            authenticated=False,
            extra_headers={"X-Eyes-Enroll-Token": token},
        )

    def heartbeat(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request_json(
            "POST", "/api/v1/node/heartbeat", payload=dict(payload)
        )

    def put_inventory(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request_json(
            "PUT", "/api/v1/node/inventory", payload=dict(payload)
        )

    def put_resources(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request_json(
            "PUT", "/api/v1/node/resources", payload=dict(payload)
        )

    def get_commands(
        self,
        *,
        cursor: int | None = None,
        wait: int = 30,
    ) -> dict[str, Any]:
        if wait < 0:
            raise ValueError("wait must not be negative")
        query: dict[str, str | int] = {"wait": wait}
        if cursor is not None:
            query["cursor"] = cursor
        return self._request_json(
            "GET", "/api/v1/node/commands", query=query
        )

    def acknowledge_command(
        self,
        command_id: str,
        status: str,
        result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not command_id:
            raise ValueError("command_id must not be empty")
        return self._request_json(
            "POST",
            f"/api/v1/node/commands/{command_id}/ack",
            payload={"status": status, "result": dict(result or {})},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, str | int] | None = None,
        authenticated: bool = True,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if authenticated and (not self.credential or not self.node_id):
            raise HubClientError("node_id and node credential are required")

        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if payload is not None:
            try:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise HubProtocolError(f"request payload is not JSON serializable: {exc}") from exc
            headers["Content-Type"] = "application/json; charset=utf-8"
        if authenticated:
            headers["Authorization"] = f"Bearer {self.credential}"
            headers["X-Eyes-Node-ID"] = self.node_id
        if extra_headers:
            headers.update(extra_headers)

        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(
                request,
                timeout=self.timeout,
                context=self.ssl_context,
            ) as response:
                response_body = response.read()
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise HubHTTPError(exc.code, error_body, str(exc.reason)) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise HubTransportError(f"cannot reach Hub: {exc}") from exc

        if not response_body:
            return {}
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HubProtocolError("Hub returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise HubProtocolError("Hub JSON response must be an object")
        return decoded


class ExponentialBackoff:
    """Bounded exponential retry delays with optional symmetric jitter."""

    def __init__(
        self,
        initial: float = 1.0,
        maximum: float = 60.0,
        multiplier: float = 2.0,
        jitter: float = 0.2,
        *,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        if initial <= 0:
            raise ValueError("initial must be positive")
        if maximum < initial:
            raise ValueError("maximum must be greater than or equal to initial")
        if multiplier < 1:
            raise ValueError("multiplier must be at least 1")
        if not 0 <= jitter <= 1:
            raise ValueError("jitter must be between 0 and 1")
        self.initial = float(initial)
        self.maximum = float(maximum)
        self.multiplier = float(multiplier)
        self.jitter = float(jitter)
        self.random_source = random_source
        self.attempt = 0

    def delay(self, attempt: int) -> float:
        """Calculate a delay for a zero-based attempt without changing state."""
        if attempt < 0:
            raise ValueError("attempt must not be negative")
        try:
            base = min(self.maximum, self.initial * self.multiplier**attempt)
        except OverflowError:
            base = self.maximum
        jitter_factor = 1 + ((self.random_source() * 2) - 1) * self.jitter
        return max(0.0, min(self.maximum, base * jitter_factor))

    def next_delay(self) -> float:
        """Return the next delay and advance the internal attempt counter."""
        delay = self.delay(self.attempt)
        self.attempt += 1
        return delay

    def reset(self) -> None:
        self.attempt = 0
