#!/usr/bin/env python3
"""Transport layer for Abaqus MCP -- TCP socket and file IPC bridge."""

from __future__ import annotations

import json
import socket
import uuid
from typing import Any
import os
import anyio

from .protocol import ProtocolError, send_message, read_message

DEFAULT_HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
DEFAULT_TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))
MAX_MESSAGE_BYTES = int(os.environ.get("ABAQUS_MCP_MAX_MESSAGE_BYTES", str(32 * 1024 * 1024)))

TRANSPORT = os.environ.get("ABAQUS_MCP_TRANSPORT", "socket").lower()
if TRANSPORT not in ("socket", "file"):
    raise ValueError(f"ABAQUS_MCP_TRANSPORT must be 'socket' or 'file', got '{TRANSPORT}'")

_file_ipc_client = None  # lazy-init singleton for file IPC mode


def _json_string(data: Any) -> str:
    """Serialize data to a compact JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def _socket_request(method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
    payload = {
        "id": str(uuid.uuid4()),
        "method": method,
        "params": {**(params or {}), "timeout": effective_timeout},
    }

    with socket.create_connection((DEFAULT_HOST, DEFAULT_PORT), timeout=effective_timeout) as sock:
        sock.settimeout(effective_timeout)
        send_message(sock, payload)
        response = read_message(sock, max_bytes=MAX_MESSAGE_BYTES)

    if response.get("id") != payload["id"]:
        raise ProtocolError("Abaqus bridge returned a mismatched response id")
    if not response.get("ok", False):
        error = response.get("error") or {}
        if isinstance(error, dict):
            raise RuntimeError(error.get("message") or json.dumps(error, ensure_ascii=False))
        raise RuntimeError(str(error))

    result = response.get("result")
    if not isinstance(result, dict):
        raise ProtocolError("Abaqus bridge returned an invalid result envelope")
    return result


def _get_file_ipc_client():
    """Lazy-init the FileIPCClient singleton."""
    global _file_ipc_client
    if _file_ipc_client is None:
        from .client import FileIPCClient
        _file_ipc_client = FileIPCClient()
    return _file_ipc_client


def _file_ipc_request(method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    """Send a request to Abaqus via file IPC and return the result."""
    client = _get_file_ipc_client()
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
    client_with_timeout = FileIPCClient(
        mcp_home=client.mcp_home,
        timeout=effective_timeout,
    )
    return client_with_timeout.request(method, params or {})


async def _bridge_request(method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    if TRANSPORT == "file":
        return await anyio.to_thread.run_sync(_file_ipc_request, method, params, timeout)
    try:
        return await anyio.to_thread.run_sync(_socket_request, method, params, timeout)
    except ConnectionRefusedError as exc:
        raise RuntimeError(
            "Cannot connect to Abaqus bridge (Connection Refused)\n"
            "Please verify:\n"
            "1. Abaqus/CAE is open and running\n"
            "2. Click Plug-ins -> ABAQUS MCP -> Start MCP Bridge in Abaqus menu\n"
            f"Bridge address: {DEFAULT_HOST}:{DEFAULT_PORT}\n"
            f"Error details: {exc}\n"
            "\n"
            "???? Abaqus ?????????\n"
            "????\n"
            "1. Abaqus/CAE ??????\n"
            "2. ? Abaqus ????? Plug-ins -> ABAQUS MCP -> Start MCP Bridge\n"
            f"?????{DEFAULT_HOST}:{DEFAULT_PORT}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            "Abaqus bridge communication timeout (Timeout)\n"
            "Abaqus may be processing a large computation or has frozen\n"
            "Try clicking Stop & Start MCP Bridge in Abaqus\n"
            f"Bridge address: {DEFAULT_HOST}:{DEFAULT_PORT}\n"
            f"Error details: {exc}\n"
            "\n"
            "Abaqus ??????\n"
            "Abaqus ??????????????\n"
            "??? Abaqus ??? Stop & Start MCP Bridge\n"
            f"?????{DEFAULT_HOST}:{DEFAULT_PORT}"
        ) from exc


async def _exec(code: str, timeout: float | None = None) -> dict[str, Any]:
    return await _bridge_request("execute", {"code": code}, timeout)
