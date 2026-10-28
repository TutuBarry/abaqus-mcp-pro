"""Accept MCP stdio recovery behavior with isolated local bridge peers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _abaqus_pids() -> list[int]:
    try:
        import psutil
    except ImportError:
        return []

    pids: list[int] = []
    for process in psutil.process_iter(["pid", "name"]):
        name = str(process.info.get("name") or "").lower()
        if name.startswith("abqcae"):
            pids.append(int(process.info["pid"]))
    return sorted(pids)


class ControlledBridge:
    """A line-delimited JSON bridge with healthy, abrupt, and silent modes."""

    def __init__(self, mode: str, port: int = 0) -> None:
        if mode not in {"healthy", "abrupt", "unresponsive"}:
            raise ValueError(f"unsupported bridge mode: {mode}")
        self.mode = mode
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", port))
        self._listener.listen(16)
        self._listener.settimeout(0.1)
        self.port = int(self._listener.getsockname()[1])
        self.requests: list[dict[str, Any]] = []
        self._thread = threading.Thread(
            target=self._serve,
            name=f"acceptance-bridge-{mode}-{self.port}",
            daemon=True,
        )
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _address = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle,
                args=(connection,),
                name=f"acceptance-bridge-request-{self.port}",
                daemon=True,
            ).start()

    def _handle(self, connection: socket.socket) -> None:
        with connection:
            if self.mode == "unresponsive":
                self._stop.wait(4.0)
                return

            data = bytearray()
            connection.settimeout(3.0)
            try:
                while b"\n" not in data:
                    chunk = connection.recv(4096)
                    if not chunk:
                        return
                    data.extend(chunk)
            except OSError:
                return

            try:
                request = json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            if not isinstance(request, dict):
                return
            self.requests.append(request)

            if self.mode == "abrupt":
                return

            response = {
                "id": request.get("id"),
                "ok": True,
                "result": {
                    "backend": "gui",
                    "abaqus_version": "acceptance-controlled",
                    "thread": "acceptance-bridge",
                    "capabilities": {
                        "protocol_version": "1.1",
                        "backend": "gui",
                        "methods": ["ping"],
                    },
                },
            }
            try:
                connection.sendall(
                    json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
                )
            except OSError:
                return

    def stop(self) -> None:
        self._stop.set()
        try:
            self._listener.close()
        finally:
            self._thread.join(timeout=2.0)


def _decode_tool_result(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        payload: Any = structured
    else:
        content = getattr(result, "content", None) or []
        text = getattr(content[0], "text", None) if content else None
        if text:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text
        else:
            payload = None
    return {
        "outcome": "tool_error" if getattr(result, "is_error", False) else "ok",
        "payload": payload,
    }


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    read_timeout: float = 20.0,
) -> dict[str, Any]:
    try:
        result = await session.call_tool(
            name,
            arguments,
            read_timeout_seconds=read_timeout,
        )
        return _decode_tool_result(result)
    except Exception as exc:  # The SDK may raise for transport-level tool failures.
        return {
            "outcome": "exception",
            "error_type": f"{type(exc).__module__}.{type(exc).__name__}",
            "error": str(exc),
        }


def _server_environment(root: Path, port: int, plugin_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH", "")
    source_path = str(root / "src")
    environment["PYTHONPATH"] = (
        source_path + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    )
    environment["ABAQUS_MCP_HOST"] = "127.0.0.1"
    environment["ABAQUS_MCP_PORT"] = str(port)
    environment["ABAQUS_MCP_TOKEN"] = ""
    environment["ABAQUS_MCP_PLUGIN_DIR"] = str(plugin_dir)
    environment["ABAQUS_MCP_AUTOSTART"] = "0"
    return environment


def _normal_server_parameters(
    root: Path,
    port: int,
    plugin_dir: Path,
) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "abaqus_mcp_pro.server"],
        cwd=str(root),
        env=_server_environment(root, port, plugin_dir),
    )


def _fault_bootstrap() -> str:
    return r"""
import atexit
import os
from pathlib import Path
import subprocess
import sys

from abaqus_mcp_pro import cae_connection, server

_children = []
_launch_count = 0


def _find_existing_cae():
    return None


def _find_command():
    return "acceptance-abaqus"


def _install_plugin():
    return Path("acceptance-plugin.py")


def _launch_cae(command, cwd=None):
    global _launch_count
    _launch_count += 1
    if _launch_count == 1:
        process = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(23)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process = subprocess.Popen(
            [
                sys.executable,
                os.environ["ABAQUS_MCP_FAULT_HELPER"],
                "--helper-bridge-port",
                os.environ["ABAQUS_MCP_PORT"],
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    _children.append(process)
    return process


def _cleanup():
    for process in _children:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


atexit.register(_cleanup)
cae_connection._find_existing_cae = _find_existing_cae
cae_connection.find_abaqus_command = _find_command
cae_connection._install_bridge_plugin = _install_plugin
cae_connection._launch_cae_process = _launch_cae
server.main()
"""


def _fault_server_parameters(
    root: Path,
    port: int,
    plugin_dir: Path,
    script: Path,
) -> StdioServerParameters:
    environment = _server_environment(root, port, plugin_dir)
    environment["ABAQUS_MCP_FAULT_HELPER"] = str(script)
    return StdioServerParameters(
        command=sys.executable,
        args=["-c", _fault_bootstrap()],
        cwd=str(root),
        env=environment,
    )


async def _drop_and_restart(root: Path, plugin_dir: Path) -> dict[str, Any]:
    first_bridge = ControlledBridge("healthy")
    parameters = _normal_server_parameters(root, first_bridge.port, plugin_dir)
    restarted_bridge = None
    abrupt_bridge = None
    try:
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                before_drop = await _call_tool(session, "ping", {"timeout": 3})
                first_bridge.stop()
                after_stop = await _call_tool(session, "ping", {"timeout": 3})

                abrupt_bridge = ControlledBridge(
                    "abrupt",
                    port=first_bridge.port,
                )
                after_abrupt_close = await _call_tool(session, "ping", {"timeout": 3})
                abrupt_bridge.stop()

                restarted_bridge = ControlledBridge(
                    "healthy",
                    port=first_bridge.port,
                )
                after_restart = await _call_tool(session, "ping", {"timeout": 3})
    finally:
        first_bridge.stop()
        if abrupt_bridge is not None:
            abrupt_bridge.stop()
        if restarted_bridge is not None:
            restarted_bridge.stop()

    passed = (
        before_drop.get("outcome") == "ok"
        and after_stop.get("outcome") != "ok"
        and after_abrupt_close.get("outcome") != "ok"
        and after_restart.get("outcome") == "ok"
    )
    return {
        "passed": passed,
        "scope": (
            "MCP stdio session survives port loss and an in-flight bridge "
            "disconnect, then reconnects without restarting MCP"
        ),
        "before_drop": before_drop,
        "after_stop": after_stop,
        "after_abrupt_close": after_abrupt_close,
        "after_restart": after_restart,
    }


async def _port_conflict(root: Path, plugin_dir: Path) -> dict[str, Any]:
    blocker = ControlledBridge("unresponsive")
    abaqus_pids_before = _abaqus_pids()
    parameters = _normal_server_parameters(root, blocker.port, plugin_dir)
    try:
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                during_conflict = await _call_tool(
                    session,
                    "connect_abaqus",
                    {"timeout": 2},
                    read_timeout=15,
                )
                abaqus_pids_after = _abaqus_pids()
                blocker.stop()

                restarted_bridge = ControlledBridge(
                    "healthy",
                    port=blocker.port,
                )
                try:
                    after_release = await _call_tool(
                        session,
                        "connect_abaqus",
                        {"timeout": 5},
                    )
                finally:
                    restarted_bridge.stop()
    finally:
        blocker.stop()

    conflict_payload = during_conflict.get("payload")
    released_payload = after_release.get("payload")
    passed = (
        isinstance(conflict_payload, dict)
        and conflict_payload.get("ok") is False
        and conflict_payload.get("status") == "bridge_unresponsive"
        and abaqus_pids_before == abaqus_pids_after
        and isinstance(released_payload, dict)
        and released_payload.get("ok") is True
        and released_payload.get("status") == "bridge_ready"
    )
    return {
        "passed": passed,
        "scope": "Occupied unresponsive port is rejected without launching CAE",
        "abaqus_pids_before": abaqus_pids_before,
        "abaqus_pids_after": abaqus_pids_after,
        "no_duplicate_cae": abaqus_pids_before == abaqus_pids_after,
        "during_conflict": during_conflict,
        "after_release": after_release,
    }


async def _process_crash(
    root: Path,
    plugin_dir: Path,
    script: Path,
) -> dict[str, Any]:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    finally:
        probe.close()

    parameters = _fault_server_parameters(root, port, plugin_dir, script)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            first_connect = await _call_tool(
                session,
                "connect_abaqus",
                {"timeout": 8},
                read_timeout=20,
            )
            second_connect = await _call_tool(
                session,
                "connect_abaqus",
                {"timeout": 8},
                read_timeout=20,
            )
            ping = await _call_tool(session, "ping", {"timeout": 3})

    first_payload = first_connect.get("payload")
    second_payload = second_connect.get("payload")
    passed = (
        isinstance(first_payload, dict)
        and first_payload.get("ok") is False
        and first_payload.get("status") == "launch_failed"
        and first_payload.get("return_code") == 23
        and isinstance(second_payload, dict)
        and second_payload.get("ok") is True
        and second_payload.get("status") == "launched_cae_bridge_ready"
        and ping.get("outcome") == "ok"
    )
    return {
        "passed": passed,
        "scope": (
            "Controlled CAE launcher exits before bridge readiness; the same "
            "MCP stdio session relaunches and reaches a healthy bridge"
        ),
        "live_cae_not_terminated": True,
        "first_connect": first_connect,
        "second_connect": second_connect,
        "ping": ping,
    }


async def _run(output: Path) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    started_at = _utc_now()
    with tempfile.TemporaryDirectory(prefix="abaqus-mcp-fault-acceptance-") as directory:
        plugin_dir = Path(directory)
        drop_restart = await _drop_and_restart(root, plugin_dir)
        port_conflict = await _port_conflict(root, plugin_dir)
        process_crash = await _process_crash(root, plugin_dir, Path(__file__).resolve())

    report = {
        "scope": "Current working tree MCP stdio bridge fault handling",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "drop_and_restart": drop_restart,
        "port_conflict": port_conflict,
        "process_crash_and_relaunch": process_crash,
        "passed": (
            drop_restart["passed"]
            and port_conflict["passed"]
            and process_crash["passed"]
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--helper-bridge-port", type=int)
    args = parser.parse_args()

    if args.helper_bridge_port is not None:
        bridge = ControlledBridge("healthy", port=args.helper_bridge_port)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            bridge.stop()
        return

    if not args.output:
        parser.error("--output is required unless --helper-bridge-port is used")
    report = asyncio.run(_run(Path(args.output)))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
