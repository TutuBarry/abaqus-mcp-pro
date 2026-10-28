"""Force-kill a disposable real GUI CAE and verify MCP bridge recovery."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROTECTED_PORT = 48152
CAE_PROCESS_PREFIX = "abqcae"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _abaqus_processes() -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        name = str(process.info.get("name") or "")
        if name.lower().startswith(CAE_PROCESS_PREFIX):
            processes.append(
                {
                    "pid": int(process.info["pid"]),
                    "ppid": int(process.info.get("ppid") or 0),
                    "name": name,
                    "cmdline": process.info.get("cmdline") or [],
                }
            )
    return sorted(processes, key=lambda item: item["pid"])


def _listener_pid(port: int) -> int | None:
    for connection in psutil.net_connections(kind="tcp"):
        address = getattr(connection, "laddr", None)
        if (
            connection.status == psutil.CONN_LISTEN
            and address is not None
            and int(getattr(address, "port", -1)) == port
        ):
            return int(connection.pid) if connection.pid is not None else None
    return None


def _wait_for_no_listener(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _listener_pid(port) is None:
            return True
        time.sleep(0.1)
    return _listener_pid(port) is None


def _target_process_group(port: int) -> dict[str, Any]:
    listener_pid = _listener_pid(port)
    if listener_pid is None:
        raise RuntimeError(f"No listener found on acceptance port {port}")

    abaqus = _abaqus_processes()
    listener = next((item for item in abaqus if item["pid"] == listener_pid), None)
    if listener is None:
        raise RuntimeError(
            f"Listener pid {listener_pid} on port {port} is not an ABQcae process"
        )

    parent_pid = listener["ppid"]
    siblings = [
        item
        for item in abaqus
        if item["ppid"] == parent_pid
    ]
    if listener["pid"] not in {item["pid"] for item in siblings}:
        siblings.append(listener)

    try:
        parent = psutil.Process(parent_pid)
        parent_info = {
            "pid": parent.pid,
            "name": parent.name(),
            "cmdline": parent.cmdline(),
        }
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        parent_info = {"pid": parent_pid, "name": "", "cmdline": []}

    return {
        "port": port,
        "listener_pid": listener_pid,
        "parent": parent_info,
        "cae_processes": sorted(siblings, key=lambda item: item["pid"]),
    }


def _kill_disposable_group(group: dict[str, Any], protected_pids: set[int]) -> dict[str, Any]:
    target_pids = {int(item["pid"]) for item in group["cae_processes"]}
    parent_pid = int(group["parent"]["pid"])
    parent_name = str(group["parent"].get("name") or "").lower()
    parent_cmdline = " ".join(str(v) for v in group["parent"].get("cmdline") or []).lower()
    parent_is_launcher = parent_name == "smapython" and "cae.pyc" in parent_cmdline
    if parent_pid and parent_is_launcher:
        target_pids.add(parent_pid)

    overlap = sorted(target_pids & protected_pids)
    if overlap:
        raise RuntimeError(f"Refusing to kill protected Abaqus pids: {overlap}")
    if group["port"] == PROTECTED_PORT:
        raise RuntimeError(f"Refusing to kill processes on protected port {PROTECTED_PORT}")

    killed: list[dict[str, Any]] = []
    for pid in sorted(target_pids, reverse=True):
        try:
            process = psutil.Process(pid)
            name = process.name()
            process.kill()
            killed.append({"pid": pid, "name": name, "kill_requested": True})
        except psutil.NoSuchProcess:
            killed.append({"pid": pid, "name": "", "already_exited": True})
        except psutil.AccessDenied as exc:
            raise RuntimeError(f"Access denied while killing disposable pid {pid}: {exc}") from exc

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        remaining = [item["pid"] for item in killed if psutil.pid_exists(item["pid"])]
        if not remaining:
            break
        time.sleep(0.1)
    return {"target_pids": sorted(target_pids), "killed": killed}


def _server_environment(port: int) -> dict[str, str]:
    environment = os.environ.copy()
    source = str(Path(__file__).resolve().parents[1] / "src")
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        source + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    )
    environment["ABAQUS_MCP_HOST"] = "127.0.0.1"
    environment["ABAQUS_MCP_PORT"] = str(port)
    environment["ABAQUS_MCP_TOKEN"] = ""
    environment["ABAQUS_MCP_AUTOSTART"] = "0"
    return environment


def _bootstrap() -> str:
    return r"""
from abaqus_mcp_pro import cae_connection, server

# The acceptance run must start a second, disposable CAE even though the
# protected live session is intentionally left open on its own bridge port.
cae_connection._find_existing_cae = lambda: None
server.main()
"""


def _server_parameters(root: Path, port: int) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-c", _bootstrap()],
        cwd=str(root),
        env=_server_environment(port),
    )


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    read_timeout: float,
) -> dict[str, Any]:
    try:
        result = await session.call_tool(
            name,
            arguments,
            read_timeout_seconds=read_timeout,
        )
    except Exception as exc:
        return {
            "outcome": "exception",
            "error_type": f"{type(exc).__module__}.{type(exc).__name__}",
            "error": str(exc),
        }

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        payload: Any = structured
    else:
        content = getattr(result, "content", None) or []
        text = getattr(content[0], "text", None) if content else None
        try:
            payload = json.loads(text) if text else None
        except json.JSONDecodeError:
            payload = text
    return {
        "outcome": "tool_error" if getattr(result, "is_error", False) else "ok",
        "payload": payload,
    }


def _payload(call: dict[str, Any]) -> dict[str, Any]:
    payload = call.get("payload")
    return payload if isinstance(payload, dict) else {}


def _select_port(requested: int) -> int:
    if requested == PROTECTED_PORT:
        raise ValueError(f"Acceptance port must not be the protected port {PROTECTED_PORT}")
    if requested:
        if _listener_pid(requested) is not None:
            raise RuntimeError(f"Requested acceptance port {requested} is already in use")
        return requested

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    workdir = Path(args.output).resolve().parent / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    port = _select_port(args.port)
    baseline = _abaqus_processes()
    protected_pids = {int(item["pid"]) for item in baseline}
    protected_listener = _listener_pid(PROTECTED_PORT)
    if protected_listener is None:
        raise RuntimeError(
            f"Protected live bridge on port {PROTECTED_PORT} is not listening"
        )

    started_at = _utc_now()
    recovered_group: dict[str, Any] | None = None
    crash: dict[str, Any] | None = None
    cleanup: dict[str, Any] | None = None
    result: dict[str, Any] = {
        "scope": "Disposable real GUI Abaqus/CAE force-kill and same MCP stdio session recovery",
        "started_at": started_at,
        "acceptance_port": port,
        "protected_port": PROTECTED_PORT,
        "protected_listener_pid_before": protected_listener,
        "protected_processes_before": baseline,
    }

    try:
        async with stdio_client(_server_parameters(root, port)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                first_connect = await _call_tool(
                    session,
                    "connect_abaqus",
                    {"cwd": str(workdir), "timeout": args.startup_timeout},
                    args.startup_timeout + 30,
                )
                first_payload = _payload(first_connect)
                result["first_connect"] = first_connect
                if not first_payload.get("ok"):
                    raise RuntimeError(f"Initial disposable CAE launch failed: {first_payload}")

                first_ping = await _call_tool(session, "ping", {"timeout": 10}, 20)
                result["first_ping"] = first_ping
                if first_ping.get("outcome") != "ok":
                    raise RuntimeError(f"Initial disposable bridge ping failed: {first_ping}")

                group = _target_process_group(port)
                group_pids = {int(item["pid"]) for item in group["cae_processes"]}
                if not group_pids:
                    raise RuntimeError("No disposable ABQcae processes were identified")
                result["disposable_process_group"] = group
                if _listener_pid(PROTECTED_PORT) != protected_listener:
                    raise RuntimeError("Protected bridge listener changed before crash test")
                if not protected_pids.issubset(
                    {int(item["pid"]) for item in _abaqus_processes()}
                ):
                    raise RuntimeError("A protected Abaqus process exited before crash test")

                crash = _kill_disposable_group(group, protected_pids)
                listener_closed = _wait_for_no_listener(port, args.crash_timeout)
                after_crash = await _call_tool(session, "ping", {"timeout": 5}, 10)
                result["crash"] = {
                    **crash,
                    "listener_closed": listener_closed,
                    "ping_after_crash": after_crash,
                }
                if not listener_closed:
                    raise RuntimeError("Disposable bridge listener remained open after force-kill")
                if after_crash.get("outcome") == "ok":
                    raise RuntimeError("Bridge ping still succeeded after disposable CAE force-kill")

                recovered_connect = await _call_tool(
                    session,
                    "connect_abaqus",
                    {"cwd": str(workdir), "timeout": args.recovery_timeout},
                    args.recovery_timeout + 30,
                )
                recovered_payload = _payload(recovered_connect)
                result["recovered_connect"] = recovered_connect
                if not recovered_payload.get("ok"):
                    raise RuntimeError(
                        f"Same MCP session failed to relaunch CAE: {recovered_payload}"
                    )

                recovered_ping = await _call_tool(session, "ping", {"timeout": 10}, 20)
                result["recovered_ping"] = recovered_ping
                if recovered_ping.get("outcome") != "ok":
                    raise RuntimeError(
                        f"Recovered disposable bridge ping failed: {recovered_ping}"
                    )

                recovered_group = _target_process_group(port)
                result["recovered_process_group"] = recovered_group
                result["passed_recovery"] = (
                    recovered_group["listener_pid"] not in {
                        int(item["pid"]) for item in group["cae_processes"]
                    }
                )
                if not result["passed_recovery"]:
                    raise RuntimeError("Recovered bridge reused a force-killed CAE process")
    finally:
        if _listener_pid(port) is not None:
            try:
                recovered_group = _target_process_group(port)
                cleanup = _kill_disposable_group(recovered_group, protected_pids)
                _wait_for_no_listener(port, args.crash_timeout)
            except Exception as exc:
                if _wait_for_no_listener(port, 5):
                    cleanup = {
                        "already_exited_during_cleanup": True,
                        "detail": str(exc),
                    }
                else:
                    cleanup = {"error": str(exc)}
        else:
            cleanup = {"already_exited_before_cleanup": True}
        result["cleanup"] = cleanup
        result["protected_processes_after"] = _abaqus_processes()
        result["protected_listener_pid_after"] = _listener_pid(PROTECTED_PORT)
        result["finished_at"] = _utc_now()
        result["protected_session_preserved"] = (
            protected_listener == result["protected_listener_pid_after"]
            and protected_pids.issubset(
                {int(item["pid"]) for item in result["protected_processes_after"]}
            )
        )
        result["passed"] = bool(
            result.get("crash", {}).get("listener_closed")
            and result.get("crash", {}).get("ping_after_crash", {}).get("outcome") != "ok"
            and result.get("recovered_ping", {}).get("outcome") == "ok"
            and result.get("passed_recovery")
            and result["protected_session_preserved"]
            and not (cleanup or {}).get("error")
            and _listener_pid(port) is None
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--startup-timeout", type=float, default=240.0)
    parser.add_argument("--recovery-timeout", type=float, default=240.0)
    parser.add_argument("--crash-timeout", type=float, default=30.0)
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), **report}, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
