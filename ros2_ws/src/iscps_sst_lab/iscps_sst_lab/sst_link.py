"""Focused SST links for two fixed sensor-to-agent connections.

The wrapper adds only a JSON envelope for the lab payload type. Encryption,
integrity, sequencing, key distribution, and peer handshakes remain entirely
the responsibility of the public iotauth API.
"""

from __future__ import annotations

import base64
import json
import queue
import socket
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

IOTAUTH_IMPORT_ERROR: Exception | None = None
try:
    from iotauth import (
        AuthConnectionError,
        IoTAuthContext,
        SecureClient,
        SecureServer,
    )

    IOTAUTH_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on environment setup
    IOTAUTH_AVAILABLE = False
    IOTAUTH_IMPORT_ERROR = exc

MAX_IMAGE_BYTES = 2_000_000
# The pinned transport accepts at most 65,536 encrypted frame bytes. Keep the
# plaintext envelope below 60 KB to leave room for the sequence number,
# authenticated-encryption metadata, padding, and frame fields.
MAX_PROTECTED_PAYLOAD_BYTES = 60_000


class SSTLinkError(RuntimeError):
    pass


class SSTPayloadError(ValueError):
    pass


def require_iotauth() -> None:
    if not IOTAUTH_AVAILABLE:
        raise SSTLinkError(
            "iotauth is not importable. Install it directly from the submodule with: "
            "python3 -m pip install third_party/iotauth/entity/python "
            f"({IOTAUTH_IMPORT_ERROR})"
        )


def is_timeout_error(exc: BaseException) -> bool:
    """Recognize wrapped socket timeouts without matching exception text."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, socket.timeout)):
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass(frozen=True)
class LinkStatus:
    state: str = "idle"
    authenticated: bool = False
    ever_authenticated: bool = False
    messages: int = 0
    connection_attempts: int = 0
    failed_attempts: int = 0
    last_error: str | None = None


@dataclass(frozen=True)
class AuthenticatedJSON:
    payload: dict[str, Any]
    received_at: float
    authenticated: bool = True


@dataclass(frozen=True)
class AuthenticatedBytes:
    metadata: dict[str, Any]
    data: bytes
    received_at: float
    authenticated: bool = True


@dataclass(frozen=True)
class SecureInputAuthContext:
    """Shared Auth state for every input link owned by one entity.

    IoTAuth rotates an entity's distribution key while issuing its first
    session key. Serializing the initial ``SecureClient.connect`` calls keeps
    two fixed sensor links from racing that rotation while still allowing both
    established channels to receive concurrently.
    """

    iotauth: Any
    connect_lock: Any

    @classmethod
    def from_config(cls, config_path: Path) -> SecureInputAuthContext:
        require_iotauth()
        return cls(
            iotauth=IoTAuthContext.from_config(Path(config_path)),
            connect_lock=threading.Lock(),
        )


def encode_json(payload: dict[str, Any]) -> bytes:
    return json.dumps({"kind": "json", "payload": payload}, separators=(",", ":")).encode(
        "utf-8"
    )


def encode_bytes(metadata: dict[str, Any], data: bytes) -> bytes:
    if len(data) > MAX_IMAGE_BYTES:
        raise SSTPayloadError(
            f"image has {len(data)} bytes; maximum is {MAX_IMAGE_BYTES}"
        )
    envelope = json.dumps(
        {
            "kind": "bytes",
            "metadata": metadata,
            "data_base64": base64.b64encode(data).decode("ascii"),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    if len(envelope) > MAX_PROTECTED_PAYLOAD_BYTES:
        raise SSTPayloadError(
            f"protected image envelope has {len(envelope)} bytes; maximum is "
            f"{MAX_PROTECTED_PAYLOAD_BYTES}. Resize or recompress the scene image."
        )
    return envelope


def decode_envelope(raw: bytes) -> tuple[str, dict[str, Any], bytes | None]:
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SSTPayloadError("protected payload is not valid UTF-8 JSON") from exc
    if not isinstance(envelope, dict):
        raise SSTPayloadError("protected payload must be a JSON object")
    kind = envelope.get("kind")
    if kind == "json":
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise SSTPayloadError("json payload must be an object")
        return "json", payload, None
    if kind == "bytes":
        metadata = envelope.get("metadata")
        encoded = envelope.get("data_base64")
        if not isinstance(metadata, dict) or not isinstance(encoded, str):
            raise SSTPayloadError("bytes payload requires metadata and data_base64")
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise SSTPayloadError("image payload is not valid base64") from exc
        if len(data) > MAX_IMAGE_BYTES:
            raise SSTPayloadError("decoded image exceeds the size limit")
        return "bytes", metadata, data
    raise SSTPayloadError(f"unknown protected payload kind: {kind!r}")


def _put_latest(target: queue.Queue[bytes], value: bytes) -> None:
    try:
        target.put_nowait(value)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(value)


class _StatusOwner:
    def __init__(self) -> None:
        self._status = LinkStatus()
        self._status_lock = threading.Lock()

    def status(self) -> LinkStatus:
        with self._status_lock:
            return replace(self._status)

    def _set_status(self, **fields: Any) -> None:
        with self._status_lock:
            self._status = replace(self._status, **fields)

    def _message(self) -> None:
        with self._status_lock:
            self._status = replace(self._status, messages=self._status.messages + 1)


class SecureSourceServer(_StatusOwner):
    """One SST server worker with a small outgoing latest-value queue."""

    def __init__(
        self,
        *,
        config_path: Path,
        host: str,
        port: int,
        timeout_s: float = 5.0,
    ) -> None:
        super().__init__()
        require_iotauth()
        self.config_path = Path(config_path)
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)
        self._outbox: queue.Queue[bytes] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def send_json(self, payload: dict[str, Any]) -> None:
        _put_latest(self._outbox, encode_json(payload))

    def send_bytes(self, metadata: dict[str, Any], image_bytes: bytes) -> None:
        _put_latest(self._outbox, encode_bytes(metadata, image_bytes))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="sst-source", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 6.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._set_status(state="stopped", authenticated=False)

    def _run(self) -> None:
        # STUDENT TODO (Part 4): accept an iotauth SecureServer channel and send
        # only the queued sensor envelopes after its SST handshake succeeds.
        raise NotImplementedError(
            "ISCPS-STUDENT-TODO(part4-secure-source): "
            "accept an iotauth SecureServer channel and send only the queued sensor envelopes "
            "after its SST handshake succeeds. See the STUDENT TODO comment above and "
            "ASSIGNMENT.md."
        )


class SecureInputClient(_StatusOwner):
    """One background SST client and one thread-safe incoming queue."""

    def __init__(
        self,
        *,
        config_path: Path,
        purpose_group: str,
        host: str,
        port: int,
        timeout_s: float = 5.0,
        auth_context: SecureInputAuthContext | None = None,
    ) -> None:
        super().__init__()
        require_iotauth()
        self.config_path = Path(config_path)
        self.purpose_group = purpose_group
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)
        self.auth_context = auth_context
        self._inbox: queue.Queue[bytes] = queue.Queue(maxsize=4)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="sst-input", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 6.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._set_status(state="stopped", authenticated=False)

    def _next(self) -> tuple[str, dict[str, Any], bytes | None, float] | None:
        try:
            raw = self._inbox.get_nowait()
        except queue.Empty:
            return None
        kind, metadata, data = decode_envelope(raw)
        return kind, metadata, data, time.time()

    def recv_json(self) -> AuthenticatedJSON | None:
        item = self._next()
        if item is None:
            return None
        kind, payload, _, received_at = item
        if kind != "json":
            raise SSTPayloadError("expected a JSON sensor payload")
        return AuthenticatedJSON(payload=payload, received_at=received_at)

    def recv_bytes(self) -> AuthenticatedBytes | None:
        item = self._next()
        if item is None:
            return None
        kind, metadata, data, received_at = item
        if kind != "bytes" or data is None:
            raise SSTPayloadError("expected a byte sensor payload")
        return AuthenticatedBytes(
            metadata=metadata,
            data=data,
            received_at=received_at,
        )

    def _run(self) -> None:
        # STUDENT TODO (Part 4): request the authorized group key, connect with
        # SecureClient, and queue plaintext only after the SST handshake.
        raise NotImplementedError(
            "ISCPS-STUDENT-TODO(part4-secure-input): "
            "request the authorized group key, connect with SecureClient, and queue plaintext only "
            "after the SST handshake. See the STUDENT TODO comment above and ASSIGNMENT.md."
        )


__all__ = [
    "AuthenticatedBytes",
    "AuthenticatedJSON",
    "IOTAUTH_AVAILABLE",
    "LinkStatus",
    "MAX_PROTECTED_PAYLOAD_BYTES",
    "SSTLinkError",
    "SSTPayloadError",
    "SecureInputAuthContext",
    "SecureInputClient",
    "SecureSourceServer",
    "decode_envelope",
    "encode_bytes",
    "encode_json",
    "is_timeout_error",
    "require_iotauth",
]
