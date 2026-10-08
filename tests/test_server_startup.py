"""Regression tests for MCP server startup and registration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def test_server_startup_registers_surface_and_installs_plugin(tmp_path: Path) -> None:
    probe = r"""
import asyncio
import json
import sys

sys.path.insert(0, sys.argv[1])
from abaqus_mcp_pro import server

async def main():
    tools = await server.mcp.list_tools()
    prompts = await server.mcp.list_prompts()
    resources = await server.mcp.list_resources()
    print(json.dumps({
        "version": server.mcp.version,
        "tools": [tool.name for tool in tools],
        "prompts": [prompt.name for prompt in prompts],
        "resources": [str(resource.uri) for resource in resources],
    }))

asyncio.run(main())
"""
    env = os.environ.copy()
    env["ABAQUS_MCP_PLUGIN_DIR"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", probe, str(SRC)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    surface = json.loads(result.stdout)

    from abaqus_mcp_pro import __version__
    assert surface["version"] == __version__
    assert {"ping", "run_python", "odb_open"} <= set(surface["tools"])
    assert "session_workflow" in surface["prompts"]
    assert "abaqus://skills/index" in surface["resources"]
    assert (tmp_path / "abaqus_mcp_pro_gui_plugin.py").is_file()
    assert not (tmp_path / "abaqus_mcp_gui_plugin.py").exists()
