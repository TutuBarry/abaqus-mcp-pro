"""ABAQUS MCP Pro - Professional MCP server suite for Abaqus/CAE.

Provides MCP tools, prompts, resources, and skills for controlling Abaqus/CAE
through an LLM agent via TCP socket or file IPC transport.

Main modules:
    abaqus_mcp_pro.server    - MCP server (stdio)
    abaqus_mcp_pro.agent     - TCP bridge agent (runs inside Abaqus)
    abaqus_mcp_pro.tools     - MCP tool definitions
    abaqus_mcp_pro.prompts   - MCP prompt definitions
    abaqus_mcp_pro.resources - MCP resource definitions
    abaqus_mcp_pro.skills    - Skills knowledge base
    abaqus_mcp_pro.transport - TCP socket / file IPC transport
    abaqus_mcp_pro.client    - TCP and file IPC clients
    abaqus_mcp_pro.cli       - CLI: check, doctor, setup
    abaqus_mcp_pro.solver_diagnosis - Solver error diagnosis
    abaqus_mcp_pro.odb_lens  - ODB KPI extraction
    abaqus_mcp_pro.capsule   - Experiment state tracking
    abaqus_mcp_pro.contracts - Physics contracts validation
    abaqus_mcp_pro.report    - Simulation report generation
    abaqus_mcp_pro.gui_plugin       - Abaqus/CAE GUI plugin (AFX menu)
    abaqus_mcp_pro.file_ipc_plugin  - File IPC plugin (runs inside Abaqus)
"""

__version__ = "1.0.0"
