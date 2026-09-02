"""Unit tests for FileIPCClient (file-based IPC transport)."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.client import FileIPCClient


class TestFileIPCClient:
    """Tests for FileIPCClient using real temp directories."""

    @pytest.fixture
    def temp_home(self):
        with TemporaryDirectory() as tmp:
            yield tmp

    def test_init_default_home(self):
        client = FileIPCClient(mcp_home="C:/test_mcp")
        assert client.mcp_home == "C:/test_mcp"
        assert client.commands_dir == Path("C:/test_mcp/commands")
        assert client.results_dir == Path("C:/test_mcp/results")

    def test_init_env_home(self, temp_home):
        with patch.dict(os.environ, {"ABAQUS_MCP_HOME": temp_home}):
            client = FileIPCClient()
            assert client.mcp_home == temp_home

    def test_init_default_home_dir(self):
        client = FileIPCClient()
        assert client.mcp_home
        assert client.commands_dir.name == "commands"
        assert client.results_dir.name == "results"

    def test_method_to_type(self):
        mapping = {
            "execute": "execute_script",
            "execute_script": "execute_script",
            "ping": "ping",
            "get_model_info": "get_model_info",
            "list_jobs": "list_jobs",
            "submit_job": "submit_job",
            "get_odb_info": "get_odb_info",
            "capture_viewport": "get_viewport_image",
            "get_viewport_image": "get_viewport_image",
            "unknown_method": "unknown_method",
        }
        for method, expected in mapping.items():
            assert FileIPCClient._method_to_type(method) == expected

    def test_adapt_result_success(self):
        file_result = {
            "id": "abc123",
            "success": True,
            "data": {"models": ["Model-1"]},
        }
        adapted = FileIPCClient._adapt_result(file_result)
        assert adapted["ok"] is True
        assert adapted["result"] == {"models": ["Model-1"]}
        assert adapted["id"] == "abc123"

    def test_adapt_result_failure(self):
        file_result = {
            "id": "abc123",
            "success": False,
            "error": "Something went wrong",
        }
        adapted = FileIPCClient._adapt_result(file_result)
        assert adapted["ok"] is False
        assert adapted["error"]["message"] == "Something went wrong"

    def test_adapt_result_failure_no_error(self):
        file_result = {
            "id": "abc123",
            "success": False,
        }
        adapted = FileIPCClient._adapt_result(file_result)
        assert adapted["ok"] is False
        assert "error" not in adapted

    def test_ping_request(self, temp_home):
        """Simulate a ping command/response cycle."""
        # Create a client pointing to temp dir
        client = FileIPCClient(mcp_home=temp_home, timeout=2.0)

        # Start a thread that simulates the Abaqus-side plugin
        # It waits for a command file, then writes a result file
        import threading

        def simulate_plugin():
            cmd_dir = Path(temp_home) / "commands"
            result_dir = Path(temp_home) / "results"
            cmd_dir.mkdir(parents=True, exist_ok=True)
            result_dir.mkdir(parents=True, exist_ok=True)

            # Wait for command file to appear
            deadline = time.time() + 5.0
            cmd_file = None
            while time.time() < deadline:
                cmd_files = list(cmd_dir.glob("cmd_*.json"))
                if cmd_files:
                    cmd_file = cmd_files[0]
                    break
                time.sleep(0.05)

            if cmd_file is None:
                return

            # Read command
            with open(cmd_file, "r", encoding="utf-8") as f:
                command = json.load(f)

            # Write result
            result_path = result_dir / f"{command['id']}.json"
            result = {
                "id": command["id"],
                "success": True,
                "data": {"response": "pong", "version": "4.0.0"},
            }
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f)

        t = threading.Thread(target=simulate_plugin, daemon=True)
        t.start()

        result = client.ping()
        assert result["ok"] is True
        assert result["result"]["response"] == "pong"

    def test_execute_request(self, temp_home):
        """Simulate an execute command/response cycle."""
        client = FileIPCClient(mcp_home=temp_home, timeout=2.0)

        import threading

        def simulate_plugin():
            cmd_dir = Path(temp_home) / "commands"
            result_dir = Path(temp_home) / "results"
            cmd_dir.mkdir(parents=True, exist_ok=True)
            result_dir.mkdir(parents=True, exist_ok=True)

            deadline = time.time() + 5.0
            cmd_file = None
            while time.time() < deadline:
                cmd_files = list(cmd_dir.glob("cmd_*.json"))
                if cmd_files:
                    cmd_file = cmd_files[0]
                    break
                time.sleep(0.05)

            if cmd_file is None:
                return

            with open(cmd_file, "r", encoding="utf-8") as f:
                command = json.load(f)

            # Verify the command type is execute_script
            assert command["type"] == "execute_script"
            assert "script" in command

            result_path = result_dir / f"{command['id']}.json"
            result = {
                "id": command["id"],
                "success": True,
                "data": {"return_value": 42},
            }
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f)

        t = threading.Thread(target=simulate_plugin, daemon=True)
        t.start()

        result = client.execute("print('hello')")
        assert result["ok"] is True

    def test_timeout(self, temp_home):
        """Request should timeout when no plugin responds."""
        client = FileIPCClient(mcp_home=temp_home, timeout=0.5)
        with pytest.raises(RuntimeError, match="timeout"):
            client.ping()

    def test_frozen_dataclass(self):
        """FileIPCClient should be immutable (frozen=True)."""
        client = FileIPCClient(mcp_home="C:/test")
        with pytest.raises(Exception):
            client.mcp_home = "C:/other"  # type: ignore

    def test_set_workdir_mapping(self, temp_home):
        """set_workdir should be mapped to execute_script with os.chdir."""
        client = FileIPCClient(mcp_home=temp_home, timeout=2.0)

        import threading

        def simulate_plugin():
            cmd_dir = Path(temp_home) / "commands"
            result_dir = Path(temp_home) / "results"
            cmd_dir.mkdir(parents=True, exist_ok=True)
            result_dir.mkdir(parents=True, exist_ok=True)

            deadline = time.time() + 5.0
            cmd_file = None
            while time.time() < deadline:
                cmd_files = list(cmd_dir.glob("cmd_*.json"))
                if cmd_files:
                    cmd_file = cmd_files[0]
                    break
                time.sleep(0.05)

            if cmd_file is None:
                return

            with open(cmd_file, "r", encoding="utf-8") as f:
                command = json.load(f)

            # Verify it's mapped to execute_script
            assert command["type"] == "execute_script"

            result_path = result_dir / f"{command['id']}.json"
            result = {
                "id": command["id"],
                "success": True,
                "data": {"working_directory": "D:/temp"},
            }
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f)

        t = threading.Thread(target=simulate_plugin, daemon=True)
        t.start()

        result = client.request("set_workdir", {"path": "D:/temp"})
        assert result["ok"] is True
