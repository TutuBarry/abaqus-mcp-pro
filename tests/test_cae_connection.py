"""Tests for local Abaqus/CAE connection management."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from abaqus_mcp_pro import cae_connection


class FakeProcess:
    def __init__(self, pid: int = 1234, return_code: int | None = None) -> None:
        self.pid = pid
        self.return_code = return_code

    def poll(self) -> int | None:
        return self.return_code


def test_connect_uses_existing_bridge_without_launching_cae(monkeypatch) -> None:
    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: "ready")
    monkeypatch.setattr(
        cae_connection,
        "_find_existing_cae",
        lambda: (_ for _ in ()).throw(AssertionError("CAE detection should not run")),
    )
    monkeypatch.setattr(
        cae_connection,
        "_launch_cae_process",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CAE should not launch")),
    )

    result = asyncio.run(cae_connection.connect_abaqus())

    assert result["ok"] is True
    assert result["status"] == "bridge_ready"
    assert result["port"] == cae_connection.DEFAULT_PORT


def test_existing_cae_requires_manual_bridge_start(monkeypatch) -> None:
    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: "unreachable")
    monkeypatch.setattr(
        cae_connection,
        "_find_existing_cae",
        lambda: {"source": "process", "pid": 99, "name": "ABQcaeK.exe"},
    )
    monkeypatch.setattr(
        cae_connection,
        "_launch_cae_process",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CAE should not launch")),
    )
    monkeypatch.setattr(
        cae_connection,
        "_install_bridge_plugin",
        lambda: (_ for _ in ()).throw(AssertionError("plugin install should not matter")),
    )

    result = asyncio.run(cae_connection.connect_abaqus())

    assert result["ok"] is False
    assert result["status"] == "existing_cae_waiting_for_manual_bridge"
    assert result["existing_cae"]["pid"] == 99
    assert "Plug-ins -> ABAQUS MCP Pro -> Start MCP Bridge" in result["message"]


def test_unresponsive_bridge_does_not_launch_duplicate_cae(monkeypatch) -> None:
    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: "unresponsive")
    monkeypatch.setattr(
        cae_connection,
        "_find_existing_cae",
        lambda: (_ for _ in ()).throw(AssertionError("CAE detection should not run")),
    )

    result = asyncio.run(cae_connection.connect_abaqus())

    assert result["ok"] is False
    assert result["status"] == "bridge_unresponsive"
    assert "ABAQUS_MCP_TOKEN" in result["message"]


def test_probe_timeout_without_listener_is_unreachable(monkeypatch) -> None:
    def timed_out(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cae_connection, "_socket_request", timed_out)
    monkeypatch.setattr(cae_connection, "_local_bridge_has_listener", lambda: False)
    monkeypatch.setattr(cae_connection, "_BRIDGE_PROBE_RETRY_DELAY", 0)

    assert cae_connection._probe_bridge() == "unreachable"


def test_probe_timeout_with_listener_is_unresponsive(monkeypatch) -> None:
    def timed_out(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cae_connection, "_socket_request", timed_out)
    monkeypatch.setattr(cae_connection, "_local_bridge_has_listener", lambda: True)
    monkeypatch.setattr(cae_connection, "_BRIDGE_PROBE_RETRY_DELAY", 0)

    assert cae_connection._probe_bridge() == "unresponsive"


def test_probe_recovers_after_transient_timeout(monkeypatch) -> None:
    calls = 0

    def transient_timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("GUI thread was briefly busy")
        return {"ok": True}

    monkeypatch.setattr(cae_connection, "_socket_request", transient_timeout)
    monkeypatch.setattr(cae_connection, "_BRIDGE_PROBE_RETRY_DELAY", 0)

    assert cae_connection._probe_bridge() == "ready"
    assert calls == 2


def test_connect_launches_cae_and_waits_for_bridge(monkeypatch) -> None:
    probes = iter(["unreachable", "ready"])
    launched: dict[str, object] = {}

    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: next(probes))
    monkeypatch.setattr(cae_connection, "_find_existing_cae", lambda: None)
    monkeypatch.setattr(cae_connection, "find_abaqus_command", lambda: "abaqus-custom")
    monkeypatch.setattr(cae_connection, "_install_bridge_plugin", lambda: Path("plugin.py"))

    def launch(command, cwd):
        launched["command"] = command
        launched["cwd"] = cwd
        return FakeProcess(pid=4321)

    monkeypatch.setattr(cae_connection, "_launch_cae_process", launch)
    monkeypatch.setattr(cae_connection, "_LAUNCH_POLL_INTERVAL", 0.001)

    result = asyncio.run(cae_connection.connect_abaqus(timeout=1))

    assert result["ok"] is True
    assert result["status"] == "launched_cae_bridge_ready"
    assert result["pid"] == 4321
    assert launched == {"command": "abaqus-custom", "cwd": None}


def test_only_mcp_launched_cae_process_gets_autostart(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_popen(command, **options):
        captured["command"] = command
        captured["env"] = options["env"]
        return FakeProcess()

    monkeypatch.setenv("ABAQUS_MCP_AUTOSTART", "0")
    monkeypatch.setattr(cae_connection.subprocess, "Popen", fake_popen)

    process = cae_connection._launch_cae_process("abaqus-custom")

    assert process.pid == 1234
    assert captured["command"] == ["abaqus-custom", "cae"]
    assert captured["env"]["ABAQUS_MCP_AUTOSTART"] == "1"
    assert os.environ["ABAQUS_MCP_AUTOSTART"] == "0"


def test_launch_failure_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: "unreachable")
    monkeypatch.setattr(cae_connection, "_find_existing_cae", lambda: None)
    monkeypatch.setattr(cae_connection, "find_abaqus_command", lambda: "missing-abaqus")
    monkeypatch.setattr(cae_connection, "_install_bridge_plugin", lambda: Path("plugin.py"))
    monkeypatch.setattr(
        cae_connection,
        "_launch_cae_process",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing-abaqus")),
    )

    result = asyncio.run(cae_connection.connect_abaqus())

    assert result["ok"] is False
    assert result["status"] == "launch_failed"
    assert "missing-abaqus" in result["message"]


def test_plugin_install_failure_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: "unreachable")
    monkeypatch.setattr(cae_connection, "_find_existing_cae", lambda: None)
    monkeypatch.setattr(cae_connection, "find_abaqus_command", lambda: "abaqus-custom")
    monkeypatch.setattr(
        cae_connection,
        "_install_bridge_plugin",
        lambda: (_ for _ in ()).throw(PermissionError("plugin directory denied")),
    )
    monkeypatch.setattr(
        cae_connection,
        "_launch_cae_process",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CAE should not launch")),
    )

    result = asyncio.run(cae_connection.connect_abaqus())

    assert result["ok"] is False
    assert result["status"] == "launch_failed"
    assert result["plugin_path"] is None
    assert "plugin directory denied" in result["message"]


def test_launch_timeout_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(cae_connection, "_probe_bridge", lambda: "unreachable")
    monkeypatch.setattr(cae_connection, "_find_existing_cae", lambda: None)
    monkeypatch.setattr(cae_connection, "find_abaqus_command", lambda: "abaqus-custom")
    monkeypatch.setattr(cae_connection, "_install_bridge_plugin", lambda: Path("plugin.py"))
    monkeypatch.setattr(cae_connection, "_launch_cae_process", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(cae_connection, "_LAUNCH_POLL_INTERVAL", 0.001)

    result = asyncio.run(cae_connection.connect_abaqus(timeout=0.01))

    assert result["ok"] is False
    assert result["status"] == "launch_timeout"
    assert result["pid"] == 1234


def test_cae_process_detection_excludes_nogui() -> None:
    assert cae_connection._looks_like_cae_process("ABQcaeK.exe")
    assert cae_connection._looks_like_cae_process("python.exe", "abaqus cae")
    assert not cae_connection._looks_like_cae_process(
        "ABQcaeK.exe", "abaqus cae noGUI=model.py"
    )


def test_cae_process_detection_prefers_direct_gui_over_launcher(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, pid: int, name: str, cmdline: list[str]) -> None:
            self.info = {"pid": pid, "name": name, "cmdline": cmdline}

    processes = [
        FakeProcess(
            23960,
            "cmd.exe",
            ["cmd.exe", "/c", r"D:\SIMULIA\Commands\abaqus.bat", "cae"],
        ),
        FakeProcess(37904, "ABQcaeK.exe", ["ABQcaeK.exe", "-cae"]),
        FakeProcess(42852, "ABQcaeG.exe", ["ABQcaeG.exe", "-cae"]),
    ]

    import psutil

    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter(processes))

    result = cae_connection._find_cae_process_with_psutil()

    assert result == {"source": "process", "pid": 37904, "name": "ABQcaeK.exe"}


def test_gui_plugin_autostart_defaults_to_off() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "abaqus_mcp_pro"
        / "gui_plugin.py"
    ).read_text(encoding="utf-8")

    assert 'os.environ.get("ABAQUS_MCP_AUTOSTART", "0")' in source
