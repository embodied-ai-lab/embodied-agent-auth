"""TCP attack helper for SST-protected scenarios."""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TcpServerStatus:
    started: bool = False
    bound: bool = False
    connections: int = 0
    tcp_interactions: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0
    last_error: str | None = None


class MaliciousTcpServer:
    """A TCP server that listens on the sensor port but does not complete
    the SST handshake.
    """

    def __init__(self, host: str, port: int, payload: bytes) -> None:
        self.host = host
        self.port = int(port)
        self.payload = payload
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = TcpServerStatus()
        self._status_lock = threading.Lock()

    @property
    def status(self) -> TcpServerStatus:
        with self._status_lock:
            return replace(self._status)

    def _set_status(self, **fields: object) -> None:
        with self._status_lock:
            self._status = replace(self._status, **fields)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._set_status(started=True)
        self._thread = threading.Thread(
            target=self._run, name="malicious-tcp-server", daemon=True
        )
        self._thread.start()
        self._ready.wait(1.0)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(1.5)

    def _run(self) -> None:
        server = socket.socket()
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(2)
            server.settimeout(0.2)
            self._set_status(bound=True, last_error=None)
            self._ready.set()
            while not self._stop.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                with connection:
                    before = self.status
                    self._set_status(
                        connections=before.connections + 1,
                    )
                    received = b""
                    sent = 0
                    try:
                        connection.settimeout(0.5)
                        received = connection.recv(4096)
                        connection.sendall(self.payload)
                        sent = len(self.payload)
                    except OSError as exc:
                        self._set_status(last_error=f"{type(exc).__name__}: {exc}")
                    after = self.status
                    if received or sent:
                        self._set_status(
                            tcp_interactions=after.tcp_interactions + 1,
                            bytes_received=after.bytes_received + len(received),
                            bytes_sent=after.bytes_sent + sent,
                        )
        except OSError as exc:
            self._set_status(last_error=f"{type(exc).__name__}: {exc}")
        finally:
            self._ready.set()
            server.close()
