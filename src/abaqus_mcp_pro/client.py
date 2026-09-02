"""Client used by the MCP server to call the Abaqus-side socket agent."""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from typing import Any

from .protocol import read_message, send_message


@dataclass(frozen=True)
class AbaqusBridgeClient:
    host: str = "127.0.0.1"
    port: int = 48152
    timeout: float = 60.0

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        request_params.setdefault("timeout", self.timeout)
        payload = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": request_params,
        }
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            send_message(sock, payload)
            response = read_message(sock)

        if response.get("id") != payload["id"]:
            raise RuntimeError("Abaqus agent returned a mismatched response id")
        if not response.get("ok", False):
            error = response.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(message or "Abaqus agent returned an error")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Abaqus agent returned an invalid result envelope")
        return result

    def ping(self) -> dict[str, Any]:
        return self.request("ping")

    def execute(self, code: str) -> dict[str, Any]:
        return self.request("execute", {"code": code})


import json
import os
import time
from pathlib import Path


@dataclass(frozen=True)
class FileIPCClient:
    """Client that communicates with Abaqus via file-based IPC (fallback transport)."""

    mcp_home: str = ""
    timeout: float = 60.0

    def __post_init__(self) -> None:
        home = self.mcp_home or os.environ.get("ABAQUS_MCP_HOME", "")
        if not home:
            home = str(Path.home() / ".abaqus-mcp-pro")
        object.__setattr__(self, "mcp_home", home)
        object.__setattr__(self, "commands_dir", Path(home) / "commands")
        object.__setattr__(self, "results_dir", Path(home) / "results")

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        cmd_id = uuid.uuid4().hex[:8]

        # Map server method to file IPC command type
        cmd_type = self._method_to_type(method)
        command: dict[str, Any] = {"id": cmd_id, "type": cmd_type, "timestamp": time.time()}

        if method == "execute":
            command["script"] = params.get("code", "")
        elif method == "execute_script":
            command["script"] = params.get("script", "")
        elif method == "set_workdir":
            # File IPC has no set_workdir - use execute_script to run os.chdir
            command["type"] = "execute_script"
            command["script"] = (
                "import os\n"
                "os.chdir(" + repr(params.get("path", "")) + ")\n"
                "result = {'working_directory': os.getcwd()}"
            )
        elif method == "submit_job":
            command["job_name"] = params.get("job_name", "")
        elif method == "get_odb_info":
            command["odb_path"] = params.get("odb_path", "")
        elif method == "capture_viewport" or method == "get_viewport_image":
            command["type"] = "get_viewport_image"
            command["viewport_name"] = params.get("viewport_name", "")
            command["format"] = params.get("image_format", "PNG")
            command["width"] = params.get("width", 800)
            command["height"] = params.get("height", 600)

        # Write command file
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        cmd_path = self.commands_dir / f"cmd_{cmd_id}.json"
        result_path = self.results_dir / f"{cmd_id}.json"

        with open(cmd_path, "w", encoding="utf-8") as f:
            json.dump(command, f, ensure_ascii=False)

        # Poll for result
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if result_path.exists():
                try:
                    with open(result_path, "r", encoding="utf-8") as f:
                        file_result = json.load(f)
                    result_path.unlink(missing_ok=True)
                    return self._adapt_result(file_result)
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(0.05)

        # Cleanup stale command
        try:
            cmd_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(
            f"File IPC timeout: no response from Abaqus in {self.timeout}s "
            f"(cmd_id={cmd_id})"
        )

    @staticmethod
    def _method_to_type(method: str) -> str:
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
        }
        return mapping.get(method, method)

    @staticmethod
    def _adapt_result(file_result: dict[str, Any]) -> dict[str, Any]:
        """Normalize file IPC result to the same format as socket bridge."""
        adapted: dict[str, Any] = {
            "id": file_result.get("id", ""),
            "ok": file_result.get("success", False),
            "result": file_result.get("data", file_result),
        }
        if file_result.get("error"):
            adapted["error"] = {"message": file_result["error"]}
        return adapted

    def ping(self) -> dict[str, Any]:
        return self.request("ping")

    def execute(self, code: str) -> dict[str, Any]:
        return self.request("execute", {"code": code})
