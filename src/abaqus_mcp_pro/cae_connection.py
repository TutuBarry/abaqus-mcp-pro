"""Connect to the local Abaqus/CAE GUI bridge.

Only CAE processes started by this module receive ``ABAQUS_MCP_AUTOSTART=1``.
An already-running CAE session is left untouched so the user can start the
bridge explicitly from the plugin menu.
"""

from __future__ import annotations

import csv
import errno
import io
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import anyio

from .commands import find_abaqus_command
from .plugin_install import install_plugin
from .transport import DEFAULT_HOST, DEFAULT_PORT, _socket_request

MANUAL_BRIDGE_INSTRUCTION = "Plug-ins -> ABAQUS MCP Pro -> Start MCP Bridge"
_BRIDGE_PROBE_TIMEOUT = 5.0
_BRIDGE_PROBE_ATTEMPTS = 2
_BRIDGE_PROBE_RETRY_DELAY = 0.25
_DEFAULT_LAUNCH_TIMEOUT = 120.0
_LAUNCH_POLL_INTERVAL = 0.5
_LAUNCH_LOCK = threading.Lock()


def _local_bridge_has_listener() -> bool | None:
    """Return whether the local bridge port has a listener when it can be determined."""
    host = DEFAULT_HOST.strip().lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return None

    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
            for connection in psutil.net_connections(kind="tcp"):
                address = getattr(connection, "laddr", None)
                if (
                    connection.status == psutil.CONN_LISTEN
                    and address is not None
                    and getattr(address, "port", None) == DEFAULT_PORT
                ):
                    return True
            return False
        except Exception:
            pass

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.bind((host, DEFAULT_PORT))
        return False
    except OSError as exc:
        code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
        if code in {errno.EADDRINUSE, 10048}:
            return True
        return None
    finally:
        probe.close()


def _probe_bridge() -> str:
    """Return ``ready``, ``unreachable``, or ``unresponsive`` for the local bridge."""
    for attempt in range(_BRIDGE_PROBE_ATTEMPTS):
        try:
            _socket_request("ping", timeout=_BRIDGE_PROBE_TIMEOUT)
            return "ready"
        except ConnectionRefusedError:
            return "unreachable"
        except TimeoutError:
            if attempt + 1 < _BRIDGE_PROBE_ATTEMPTS:
                time.sleep(_BRIDGE_PROBE_RETRY_DELAY)
                continue
        except Exception:
            return "unresponsive"

    return "unreachable" if _local_bridge_has_listener() is False else "unresponsive"


def _looks_like_cae_process(name: str, command_line: str = "") -> bool:
    name_lower = Path(str(name or "")).name.lower()
    command_lower = str(command_line or "").lower()
    if "nogui" in command_lower:
        return False
    if "abq" in name_lower and "cae" in name_lower:
        return True
    combined = name_lower + " " + command_lower
    return (
        ("abaqus" in combined or "abq" in combined)
        and re.search(r"(^|[/\\\s])cae([=\s]|$)", command_lower) is not None
    )


def _cae_process_priority(name: str, command_line: str = "") -> int:
    """Rank direct CAE executables ahead of launcher or wrapper processes."""
    name_lower = Path(str(name or "")).name.lower()
    command_lower = str(command_line or "").lower()
    if "abq" in name_lower and "cae" in name_lower:
        return 0
    if re.search(r"(^|[/\\\s])abq[a-z0-9_-]*cae[a-z0-9_-]*\.exe", command_lower):
        return 0
    if "abaqus" in (name_lower + " " + command_lower):
        return 1
    return 2


def _find_cae_process_with_psutil() -> dict[str, Any] | None:
    try:
        import psutil
    except ImportError:
        return None

    try:
        processes = psutil.process_iter(["pid", "name", "cmdline"])
    except Exception:
        return None

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for process in processes:
        try:
            info = process.info
            command_parts = info.get("cmdline") or []
            command_line = " ".join(str(part) for part in command_parts)
            if _looks_like_cae_process(info.get("name") or "", command_line):
                candidate = {
                    "source": "process",
                    "pid": info.get("pid"),
                    "name": info.get("name") or "",
                }
                priority = _cae_process_priority(candidate["name"], command_line)
                candidates.append((priority, candidate["pid"] or 0, candidate))
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def _find_cae_process_fallback() -> dict[str, Any] | None:
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for row in csv.reader(io.StringIO(result.stdout)):
                if not row:
                    continue
                name = row[0]
                if _looks_like_cae_process(name):
                    pid = int(row[1]) if len(row) > 1 and row[1].isdigit() else None
                    return {"source": "process", "pid": pid, "name": name}
            return None

        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,args="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 2:
                continue
            pid, name = parts[:2]
            command_line = parts[2] if len(parts) > 2 else ""
            if _looks_like_cae_process(name, command_line):
                return {
                    "source": "process",
                    "pid": int(pid) if pid.isdigit() else None,
                    "name": name,
                }
    except Exception:
        return None
    return None


def _find_cae_window() -> dict[str, Any] | None:
    try:
        from .pywinauto_tools import find_abaqus_window_and_app

        _application, window = find_abaqus_window_and_app()
        if window is None or not window.exists() or not window.is_visible():
            return None
        return {
            "source": "window",
            "title": window.window_text(),
        }
    except Exception:
        return None


def _find_existing_cae() -> dict[str, Any] | None:
    return _find_cae_process_with_psutil() or _find_cae_process_fallback() or _find_cae_window()


def _install_bridge_plugin() -> Path:
    return install_plugin()


def _launch_log_path() -> Path:
    return Path(tempfile.gettempdir()) / "ABAQUS_MCP_cae_launch.log"


def _launch_cae_process(command: str, cwd: str | None = None) -> subprocess.Popen:
    environment = os.environ.copy()
    environment["ABAQUS_MCP_AUTOSTART"] = "1"
    log_path = _launch_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    options: dict[str, Any] = {
        "cwd": cwd or None,
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True

    with log_path.open("a", encoding="utf-8", buffering=1) as log:
        options["stdout"] = log
        process = subprocess.Popen([command, "cae"], **options)
    return process


def _base_result() -> dict[str, Any]:
    return {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "manual_bridge_instruction": MANUAL_BRIDGE_INSTRUCTION,
    }


def _build_connection_plan(command: str, cwd: str | None) -> dict[str, Any]:
    with _LAUNCH_LOCK:
        bridge_state = _probe_bridge()
        if bridge_state == "ready":
            return {"kind": "bridge_ready"}
        if bridge_state == "unresponsive":
            return {"kind": "bridge_unresponsive"}

        existing_cae = _find_existing_cae()
        if existing_cae is not None:
            return {"kind": "existing_cae", "existing_cae": existing_cae}

        plugin_path: Path | None = None
        try:
            plugin_path = _install_bridge_plugin()
            process = _launch_cae_process(command, cwd)
        except Exception as exc:
            return {
                "kind": "launch_failed",
                "error": str(exc),
                "abaqus_command": command,
                "plugin_path": str(plugin_path) if plugin_path is not None else None,
            }
        return {
            "kind": "launched",
            "process": process,
            "abaqus_command": command,
            "plugin_path": str(plugin_path),
            "log_path": str(_launch_log_path()),
        }


async def connect_abaqus(timeout: float | None = None, cwd: str = "") -> dict[str, Any]:
    """Connect to local Abaqus/CAE, launching the GUI only when CAE is not running.

    An existing CAE session is never automated through its plugin menu. If the
    bridge is not listening, the caller must ask the user to click
    ``Plug-ins -> ABAQUS MCP Pro -> Start MCP Bridge``.
    """
    effective_timeout = _DEFAULT_LAUNCH_TIMEOUT if timeout is None else float(timeout)
    if effective_timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    command = find_abaqus_command()
    workdir = cwd.strip() or None
    plan = await anyio.to_thread.run_sync(_build_connection_plan, command, workdir)
    kind = plan["kind"]

    if kind == "bridge_ready":
        return {
            **_base_result(),
            "ok": True,
            "status": "bridge_ready",
            "message": (
                "The Abaqus MCP bridge is already reachable at "
                f"{DEFAULT_HOST}:{DEFAULT_PORT}."
            ),
        }
    if kind == "bridge_unresponsive":
        return {
            **_base_result(),
            "ok": False,
            "status": "bridge_unresponsive",
            "message": (
                "The local bridge port is not healthy. Abaqus/CAE was not "
                "started automatically. Verify ABAQUS_MCP_TOKEN or restart "
                f"the bridge with {MANUAL_BRIDGE_INSTRUCTION}."
            ),
        }
    if kind == "existing_cae":
        return {
            **_base_result(),
            "ok": False,
            "status": "existing_cae_waiting_for_manual_bridge",
            "existing_cae": plan["existing_cae"],
            "message": (
                "Abaqus/CAE is already running, but the MCP bridge is not "
                "reachable. No CAE or bridge was started automatically. In "
                f"Abaqus, click {MANUAL_BRIDGE_INSTRUCTION}."
            ),
        }
    if kind == "launch_failed":
        return {
            **_base_result(),
            "ok": False,
            "status": "launch_failed",
            "error": plan["error"],
            "abaqus_command": plan["abaqus_command"],
            "plugin_path": plan["plugin_path"],
            "message": f"Failed to start Abaqus/CAE: {plan['error']}",
        }

    process = plan["process"]
    deadline = time.monotonic() + effective_timeout
    while True:
        bridge_state = await anyio.to_thread.run_sync(_probe_bridge)
        if bridge_state == "ready":
            return {
                **_base_result(),
                "ok": True,
                "status": "launched_cae_bridge_ready",
                "pid": process.pid,
                "abaqus_command": plan["abaqus_command"],
                "plugin_path": plan["plugin_path"],
                "log_path": plan["log_path"],
                "message": (
                    "Abaqus/CAE was started by MCP and the local bridge is "
                    f"ready at {DEFAULT_HOST}:{DEFAULT_PORT}."
                ),
            }

        return_code = process.poll()
        if return_code is not None:
            return {
                **_base_result(),
                "ok": False,
                "status": "launch_failed",
                "pid": process.pid,
                "return_code": return_code,
                "abaqus_command": plan["abaqus_command"],
                "plugin_path": plan["plugin_path"],
                "log_path": plan["log_path"],
                "message": (
                    f"Abaqus/CAE launcher exited with code {return_code}. "
                    f"See {plan['log_path']}."
                ),
            }

        if time.monotonic() >= deadline:
            return {
                **_base_result(),
                "ok": False,
                "status": "launch_timeout",
                "pid": process.pid,
                "abaqus_command": plan["abaqus_command"],
                "plugin_path": plan["plugin_path"],
                "log_path": plan["log_path"],
                "message": (
                    f"Abaqus/CAE is still running, but the MCP bridge did not "
                    f"become ready within {effective_timeout:g} seconds. See "
                    f"{plan['log_path']}."
                ),
            }

        await anyio.sleep(_LAUNCH_POLL_INTERVAL)
