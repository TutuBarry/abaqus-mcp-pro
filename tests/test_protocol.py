"""Unit tests for abaqus_mcp_pro.protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.protocol import ProtocolError, read_message, send_message


class TestProtocolError:
    def test_is_runtime_error(self):
        assert issubclass(ProtocolError, RuntimeError)

    def test_message(self):
        e = ProtocolError("test message")
        assert str(e) == "test message"


class TestSendMessage:
    def test_send_message_basic(self):
        sock = MagicMock()
        payload = {"method": "ping", "id": "abc"}
        send_message(sock, payload)
        sock.sendall.assert_called_once()
        sent_data = sock.sendall.call_args[0][0]
        assert sent_data.endswith(b"\n")
        decoded = json.loads(sent_data[:-1].decode("utf-8"))
        assert decoded == payload

    def test_send_message_empty(self):
        sock = MagicMock()
        payload = {}
        send_message(sock, payload)
        sock.sendall.assert_called_once()
        sent_data = sock.sendall.call_args[0][0]
        assert sent_data == b"{}\n"

    def test_send_message_non_ascii(self):
        sock = MagicMock()
        payload = {"message": "hello world"}
        send_message(sock, payload)
        sock.sendall.assert_called_once()
        sent_data = sock.sendall.call_args[0][0]
        decoded = json.loads(sent_data[:-1].decode("utf-8"))
        assert decoded["message"] == "hello world"


class TestReadMessage:
    def test_read_message_simple(self):
        sock = MagicMock()
        payload = {"result": "ok"}
        data = json.dumps(payload).encode("utf-8") + b"\n"
        sock.recv.side_effect = [data]
        result = read_message(sock)
        assert result == payload

    def test_read_message_chunked(self):
        sock = MagicMock()
        payload = {"result": "ok"}
        data = json.dumps(payload).encode("utf-8") + b"\n"
        # Split into two chunks
        mid = len(data) // 2
        sock.recv.side_effect = [data[:mid], data[mid:]]
        result = read_message(sock)
        assert result == payload

    def test_read_message_non_dict(self):
        sock = MagicMock()
        data = b'["not a dict"]\n'
        sock.recv.side_effect = [data]
        with pytest.raises(ProtocolError, match="must be a JSON object"):
            read_message(sock)

    def test_read_message_invalid_json(self):
        sock = MagicMock()
        data = b"not json\n"
        sock.recv.side_effect = [data]
        with pytest.raises(ProtocolError, match="invalid JSON"):
            read_message(sock)

    def test_read_message_socket_closed(self):
        sock = MagicMock()
        sock.recv.side_effect = [b""]
        with pytest.raises(ProtocolError, match="socket closed"):
            read_message(sock)

    def test_read_message_exceeds_max_bytes(self):
        sock = MagicMock()
        # Simulate receiving data that never contains a newline
        chunk = b"x" * 4096
        sock.recv.side_effect = [chunk] * 1000  # > 16MB default
        with pytest.raises(ProtocolError, match="exceeded"):
            read_message(sock, max_bytes=1024)

    def test_read_message_with_custom_max_bytes(self):
        sock = MagicMock()
        payload = {"result": "ok"}
        data = json.dumps(payload).encode("utf-8") + b"\n"
        sock.recv.side_effect = [data]
        result = read_message(sock, max_bytes=1024 * 1024)
        assert result == payload


import pytest
