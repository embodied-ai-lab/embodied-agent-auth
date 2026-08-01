from __future__ import annotations

import base64
import json
import socket

import pytest
from iscps_sst_lab.malicious_tcp_server import MaliciousTcpServer
from iscps_sst_lab.sst_link import (
    MAX_PROTECTED_PAYLOAD_BYTES,
    SSTPayloadError,
    decode_envelope,
    encode_bytes,
    encode_json,
    is_timeout_error,
)


def test_json_payload_round_trip():
    raw = encode_json({"distance_m": 0.6, "source": "net1.distance_sensor"})
    kind, payload, data = decode_envelope(raw)
    assert kind == "json"
    assert payload["distance_m"] == 0.6
    assert data is None


def test_image_payload_round_trip_and_size_measurement(green_image):
    raw = encode_bytes({"source": "net1.vision_sensor"}, green_image)
    kind, metadata, data = decode_envelope(raw)
    assert kind == "bytes"
    assert metadata["source"] == "net1.vision_sensor"
    assert data == green_image
    expected_base64 = len(base64.b64encode(green_image))
    assert len(raw) > expected_base64
    assert len(raw) < expected_base64 + 200
    assert len(raw) < MAX_PROTECTED_PAYLOAD_BYTES


def test_malformed_payload_rejected():
    with pytest.raises(SSTPayloadError):
        decode_envelope(b"not json")
    bad = json.dumps(
        {"kind": "bytes", "metadata": {}, "data_base64": "%%%"}
    ).encode()
    with pytest.raises(SSTPayloadError):
        decode_envelope(bad)


def test_oversized_protected_image_envelope_is_rejected_before_send():
    with pytest.raises(SSTPayloadError, match="Resize or recompress"):
        encode_bytes({"source": "net1.vision_sensor"}, b"x" * 50_000)


def test_wrapped_timeout_is_detected_by_exception_type():
    try:
        try:
            raise TimeoutError("localized message")
        except TimeoutError as cause:
            raise RuntimeError("wrapper without timeout text") from cause
    except RuntimeError as error:
        assert is_timeout_error(error)


def test_non_timeout_transport_error_is_not_misclassified():
    assert not is_timeout_error(ConnectionRefusedError("timed out is only text"))


def test_malicious_tcp_server_records_bind_connection_and_tcp_interaction():
    try:
        probe = socket.socket()
    except PermissionError:
        pytest.skip("execution sandbox forbids local sockets")
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    server = MaliciousTcpServer("127.0.0.1", port, b"not-an-sst-frame")
    server.start()
    assert server.status.started
    assert server.status.bound
    with socket.create_connection(("127.0.0.1", port), timeout=1.0) as client:
        client.sendall(b"malicious-handshake-one")
        assert client.recv(100) == b"not-an-sst-frame"
    server.stop()

    status = server.status
    assert status.connections == 1
    assert status.tcp_interactions == 1
    assert status.bytes_received == len(b"malicious-handshake-one")
    assert status.bytes_sent == len(b"not-an-sst-frame")
