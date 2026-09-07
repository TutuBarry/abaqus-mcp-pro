#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abaqus MCP Pro Server v1.0.0.

This stdio MCP server talks to a live Abaqus/CAE GUI bridge over a local TCP
socket. The socket bridge gives lower-latency interaction than the older
commands/results file queue while preserving the existing Abaqus-specific tools.
"""

from __future__ import annotations


from mcp.server.mcpserver import MCPServer

from .tools import register_tools
from .resources import register_resources
from .prompts import register_prompts
from .skills import register_skill_resources

INSTRUCTIONS = """You are controlling a live Abaqus/CAE session through MCP.

Use small validated Python chunks instead of one large script. Set a clean
working directory before creating jobs. Prefer named sets and named surfaces
over fragile raw-coordinate selections for loads, boundary conditions, section
assignments, and interactions. When API behavior is uncertain, inspect the live
Abaqus objects first with run_python before continuing.

--- SKILLS KNOWLEDGE BASE ---
Before starting any Abaqus task, use the available prompts and resources:

PROMPTS (guided workflows -- call these FIRST for new tasks):
- setup_static_analysis, setup_contact_analysis, setup_modal_analysis,
  setup_thermal_analysis, setup_dynamic_analysis, setup_coupled_analysis,
  setup_fatigue_analysis, setup_optimization
- define_material, setup_mesh, extract_odb_results, debug_job
- session_workflow (general orientation)

RESOURCES (reference documentation -- read AFTER prompts for details):
The skills index is at abaqus://skills/index. Key skills by category:

Modeling: abaqus://skills/geometry, abaqus://skills/material, abaqus://skills/mesh, abaqus://skills/interaction
Setup: abaqus://skills/step, abaqus://skills/boundary-condition, abaqus://skills/load, abaqus://skills/output, abaqus://skills/amplitude, abaqus://skills/field
Execution: abaqus://skills/job, abaqus://skills/odb, abaqus://skills/export
Analysis workflows: abaqus://skills/static-analysis, abaqus://skills/modal-analysis, abaqus://skills/contact-analysis, abaqus://skills/dynamic-analysis, abaqus://skills/thermal-analysis, abaqus://skills/fatigue-analysis, abaqus://skills/coupled-analysis
Optimization: abaqus://skills/optimization, abaqus://skills/topology-optimization, abaqus://skills/shape-optimization
Reference: abaqus://skills/units, abaqus://skills/docs

For a full list of all available skills, read abaqus://skills/list.
Always read the relevant skill before executing a new type of analysis.

--- EXECUTION MODES ---
This server supports three execution modes for talking to Abaqus:

1. TCP BRIDGE (default) -- Requires the Abaqus/CAE GUI with the bridge plugin loaded.
   Fastest, most capable mode. Use for interactive modeling and post-processing.

2. NO-GUI SUBPROCESS -- Uses "abaqus python" and "abaqus cae noGUI=" via subprocess.
   No GUI needed. Ideal for headless servers, CI/CD, and batch jobs.
   Tools: run_python_no_gui, abaqus_cae_no_gui, submit_job_no_gui, check_job_status_nogui,
   get_abaqus_command_path.
   Set ABAQUS_COMMAND env var to specify the Abaqus executable path.

3. PYWINAUTO GUI AUTOMATION -- Non-invasive control of an existing Abaqus/CAE window.
   No plugin installation needed. Uses Windows UI Automation to send scripts via File->Run Script.
   Tools: find_abaqus_window, execute_script_in_abaqus_gui, get_abaqus_gui_message_log.
   Requires: pip install pywinauto pygetwindow psutil pywin32

Always check which mode is available before choosing a tool. Prefer mode 1 when the bridge
is connected, mode 2 for headless/automated work, and mode 3 as a fallback when the bridge
plugin can't be installed.
"""


def _ensure_gui_plugin() -> None:
    """Install the GUI plugin silently if not already present."""
    try:
        import shutil
        from importlib import resources
        from pathlib import Path

        target_dir = Path(os.environ.get("ABAQUS_MCP_PLUGIN_DIR", Path.home() / "abaqus_plugins"))
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "abaqus_mcp_gui_plugin.py"

        source = resources.files("abaqus_mcp_pro").joinpath("gui_plugin.py")
        with resources.as_file(source) as src:
            if target.exists() and target.read_bytes() == Path(src).read_bytes():
                return
            shutil.copy2(src, target)
    except Exception:
        pass


_ensure_gui_plugin()

mcp = MCPServer("abaqus-mcp-pro", instructions=INSTRUCTIONS)

register_tools(mcp)
register_prompts(mcp)
register_resources(mcp, INSTRUCTIONS)
register_skill_resources(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()