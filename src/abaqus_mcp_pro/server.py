#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abaqus MCP Pro Server v1.0.0.

This stdio MCP server talks to a live Abaqus/CAE GUI bridge over a local TCP
socket. The socket bridge gives lower-latency interaction than the older
commands/results file queue while preserving the existing Abaqus-specific tools.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

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

PROMPTS (guided workflows — call these FIRST for new tasks):
- setup_static_analysis, setup_contact_analysis, setup_modal_analysis,
  setup_thermal_analysis, setup_dynamic_analysis, setup_coupled_analysis,
  setup_fatigue_analysis, setup_optimization
- define_material, setup_mesh, extract_odb_results, debug_job
- session_workflow (general orientation)

RESOURCES (reference documentation — read AFTER prompts for details):
The skills index is at abaqus://skills/index. Key skills by category:

Modeling: abaqus://skills/geometry, abaqus://skills/material, abaqus://skills/mesh, abaqus://skills/interaction
Setup: abaqus://skills/step, abaqus://skills/boundary-condition, abaqus://skills/load, abaqus://skills/output, abaqus://skills/amplitude, abaqus://skills/field
Execution: abaqus://skills/job, abaqus://skills/odb, abaqus://skills/export
Analysis workflows: abaqus://skills/static-analysis, abaqus://skills/modal-analysis, abaqus://skills/contact-analysis, abaqus://skills/dynamic-analysis, abaqus://skills/thermal-analysis, abaqus://skills/fatigue-analysis, abaqus://skills/coupled-analysis
Optimization: abaqus://skills/optimization, abaqus://skills/topology-optimization, abaqus://skills/shape-optimization
Reference: abaqus://skills/units, abaqus://skills/docs

For a full list of all available skills, read abaqus://skills/list.
Always read the relevant skill before executing a new type of analysis.
"""

mcp = FastMCP("abaqus-mcp-pro", instructions=INSTRUCTIONS)

register_tools(mcp)
register_prompts(mcp)
register_resources(mcp, INSTRUCTIONS)
register_skill_resources(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
