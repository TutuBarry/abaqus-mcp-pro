"""CLI entry points for diagnostics, connectivity check, and plugin setup."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from .client import AbaqusBridgeClient


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows to avoid GBK encoding errors."""
    if sys.platform == "win32":
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream is not None:
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except (AttributeError, OSError):
                    pass


def _print_json(label: str, payload: dict[str, Any]) -> None:
    print(f"{label}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _entrypoint_path(command: str) -> str | None:
    """Find the path to a console_script entry point.
    
    Uses shutil.which() for PATH-based lookup, with fallback to
    importlib.metadata for packages installed in development mode.
    """
    path = shutil.which(command)
    if path is not None:
        return path
    # Fallback: check entry_points for development installs
    try:
        eps = metadata.entry_points(group="console_scripts")
        for ep in eps:
            if ep.name == command:
                return ep.value
    except Exception:
        pass
    return None


def _static_diagnostics() -> dict[str, Any]:
    try:
        version = metadata.version("abaqus-mcp-pro")
    except metadata.PackageNotFoundError:
        version = "unknown"

    return {
        "package": {
            "name": "abaqus-mcp-pro",
            "version": version,
        },
        "runtime": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "entrypoints": {
            "abaqus-mcp-pro-server": _entrypoint_path("abaqus-mcp-pro-server"),
            "abaqus-mcp-pro-check": _entrypoint_path("abaqus-mcp-pro-check"),
            "abaqus-mcp-pro-doctor": _entrypoint_path("abaqus-mcp-pro-doctor"),
            "abaqus-mcp-pro-setup": _entrypoint_path("abaqus-mcp-pro-setup"),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abaqus-mcp-pro")
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser(
        "check",
        help="Check connectivity to the running Abaqus GUI plugin.",
    )
    check_parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    check_parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    check_parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10")),
    )
    check_parser.add_argument(
        "--code",
        default="import sys\nresult = {'python': sys.version.split()[0], 'ok': True}",
        help="Python code to execute in the Abaqus-side agent.",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Print installation and runtime diagnostics.",
    )
    doctor_parser.add_argument(
        "--verify-connection",
        action="store_true",
        help="Also ping the running Abaqus GUI plugin after printing static diagnostics.",
    )
    doctor_parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    doctor_parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    doctor_parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10")),
    )

    subparsers.add_parser(
        "setup",
        help="Install GUI plugin for Abaqus/CAE.",
    )

    return parser


def _check_main(args: argparse.Namespace) -> None:
    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        ping = client.ping()
        execution = client.execute(args.code)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Abaqus MCP Pro agent is reachable.")
    _print_json("Ping", ping)
    _print_json("Execution", execution)


def _doctor_main(args: argparse.Namespace) -> None:
    diagnostics = _static_diagnostics()
    _print_json("Diagnostics", diagnostics)
    if not args.verify_connection:
        return

    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        ping = client.ping()
    except Exception as exc:
        print(f"Connection check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    _print_json("Connection", ping)


def _setup_main(args: argparse.Namespace) -> None:
    """Copy the Abaqus GUI plugin."""
    target_dir = Path(os.environ.get("ABAQUS_MCP_PLUGIN_DIR", Path.home() / "abaqus_plugins"))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "abaqus_mcp_pro_gui_plugin.py"

    package_files = resources.files("abaqus_mcp_pro")
    source = package_files.joinpath("gui_plugin.py")
    with resources.as_file(source) as src:
        if target.exists() and target.read_bytes() == Path(src).read_bytes():
            print(f"Plugin already up to date: {target}")
        else:
            shutil.copy2(src, target)
            print(f"Installed GUI plugin to: {target}")

    print()
    print("Restart Abaqus/CAE, then activate:")
    print("Plug-ins > ABAQUS MCP Pro > Start MCP Bridge")


def main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args()
    command = args.command or "check"

    if command == "check":
        _check_main(args)
    elif command == "doctor":
        _doctor_main(args)
    elif command == "setup":
        _setup_main(args)
    else:
        parser.error(f"unknown command: {command}")


def check_main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(["check", *sys.argv[1:]])
    _check_main(args)


def doctor_main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(["doctor", *sys.argv[1:]])
    _doctor_main(args)


def setup_main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(["setup", *sys.argv[1:]])
    _setup_main(args)


if __name__ == "__main__":
    main()
