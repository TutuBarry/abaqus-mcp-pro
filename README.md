# ABAQUS MCP Pro

Professional MCP server suite for Abaqus/CAE -- 100+ tools, dual transport, capsule tracking, physics contracts, and skills integration (Codex, Claude, etc.).

## Architecture

```
MCP Client (Codex/Claude)
    |
    v  stdio
mcp server (server.py) <-- abaqus-mcp-pro package
    |
    v  TCP socket (localhost:48152)
Abaqus GUI plugin (gui_plugin.py / agent.py)
    |
    v  Abaqus Python API
Abaqus/CAE Kernel
```

The MCP server runs as a subprocess of the AI client. When the client invokes a tool (e.g. `run_python`), the server forwards the request over a TCP socket to a lightweight agent running inside Abaqus/CAE. The agent executes the code in the Abaqus Python kernel and returns results.

## Features

- **TCP socket bridge** -- 10-50ms latency vs 100-200ms for file-based IPC
- **AST error diagnostics** -- auto-analyzes KeyError, AttributeError, NameError, TypeError and suggests fixes
- **22 MCP tools** -- Full Abaqus automation: model query, job management, ODB inspection, KPI extraction, capsule tracking, physics contracts, report generation, viewport capture
- **13 MCP prompts** -- Guided workflows for static, dynamic, modal, thermal, contact, fatigue, coupled, optimization, material, mesh, ODB extraction, and job debugging
- **74 MCP resources** -- Session telemetry, skills knowledge base, CAE-Agent-Hub integration
- **AST error diagnostics** -- Auto-analyzes KeyError, AttributeError, NameError, TypeError and suggests fixes
- **3 CLI tools** -- check, doctor, setup
- **Dual transport** -- TCP socket (primary) + file IPC (fallback)
- **noGUI mode** -- run Abaqus in batch mode without GUI

## Installation

### Prerequisites

- Python 3.10+
- Abaqus 2024+ (with Python 3.10)
- MCP-compatible AI client (Codex, Claude Desktop, etc.)

### Install the package

```bash
pip install -e .
```

### Install the Abaqus GUI plugin

```bash
abaqus-mcp-pro-setup
```

Or manually copy `src/abaqus_mcp_pro/gui_plugin.py` to your Abaqus plugins directory (typically `~/abaqus_plugins/`).

## Usage

### 1. Start Abaqus/CAE

Launch Abaqus/CAE normally. Then activate the plugin:

**Plug-ins > ABAQUS MCP Pro > Start MCP Bridge**

### 2. Configure your MCP client

Add to your MCP client configuration (e.g. `mcp_config.json` for Codex):

```json
{
  "mcpServers": {
    "abaqus-mcp-pro": {
      "command": "abaqus-mcp-pro-server",
      "args": []
    }
  }
}
```

### 3. Use the tools

Once connected, the AI client can use any of the 22 tools:

| Tool | Description |
|------|-------------|
| `ping` | Check if the bridge is reachable + session status |
| `check_abaqus_connection` | Human-readable connection status |
| `run_python` | Execute arbitrary Python code in Abaqus kernel |
| `execute_script` | Compatibility wrapper returning stdout text |
| `set_workdir` | Change the Abaqus working directory |
| `get_model_info` | List parts, materials, steps, loads, BCs |
| `list_jobs` | List all jobs and their status |
| `submit_job` | Submit a job and wait for completion |
| `monitor_job_status` | Tail .sta/.msg diagnostics |
| `diagnose_job` | Solver Doctor: 40+ error patterns auto-diagnosis |
| `inspect_odb` | Read-only ODB: frame, variable, section info |
| `get_odb_info` | Compatibility wrapper for inspect_odb |
| `extract_kpis` | ODB Lens: extract KPI values (stress, displacement, etc.) |
| `create_capsule` | Save experiment state snapshot (Capsule) |
| `list_capsules` | List all saved experiment capsules |
| `load_capsule` | Load a saved experiment capsule |
| `delete_capsule` | Delete a saved experiment capsule |
| `compare_capsules` | Diff two capsules (model, KPI, file changes) |
| `check_physics_contracts` | Validate physics contracts (range, threshold, pct change) |
| `generate_report` | Generate simulation report (Markdown) |
| `capture_viewport` | Capture viewport as base64 image (PNG/TIFF/SVG) |
| `get_viewport_image` | Compatibility wrapper returning data URI |

### noGUI Mode

Run Abaqus in batch mode with the TCP agent:

```bash
abaqus cae noGUI=scripts/start_abaqus_mcp_pro_agent.py
```

Or with the file IPC fallback:

```bash
abaqus cae noGUI=scripts/start_abaqus_mcp_pro_ipc.py
```

### CLI Diagnostics

```bash
# Check connectivity to the running Abaqus bridge
abaqus-mcp-pro-check

# Full diagnostics
abaqus-mcp-pro-doctor

# Install/update GUI plugin
abaqus-mcp-pro-setup
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP host for the bridge |
| `ABAQUS_MCP_PORT` | `48152` | TCP port for the bridge |
| `ABAQUS_MCP_TIMEOUT` | `60` | Socket timeout in seconds |
| `ABAQUS_MCP_MAX_MESSAGE_BYTES` | `33554432` | Max message size |
| `ABAQUS_MCP_PLUGIN_DIR` | `~/abaqus_plugins` | Plugin install directory |
| `ABAQUS_MCP_HOME` | auto-detect | Working directory for file IPC |

## Examples

See the `examples/` directory for Abaqus Python scripts:

- `abaqus_cantilever_classic.py` -- Cantilever beam static analysis
- `abaqus_tensile_bar_classic.py` -- Tensile bar with necking
- `show_tensile_result_viewport.py` -- Post-processing visualization

## Project Structure

```
abaqus-mcp-pro/
+-- pyproject.toml           # Package metadata
+-- README.md                # This file
+-- src/abaqus_mcp_pro/
|   +-- __init__.py          # Package init
|   +-- server.py            # MCP stdio server (entry point, 67 lines)
|   +-- tools.py             # 22 MCP tools with register_tools()
|   +-- resources.py         # 3 MCP resources with register_resources()
|   +-- prompts.py           # 13 MCP prompts with register_prompts()
|   +-- skills.py            # 74 MCP skill resources with register_skill_resources()
|   +-- transport.py         # Socket + file IPC transport layer
|   +-- solver_diagnosis.py  # Solver Doctor: 40+ error patterns
|   +-- odb_lens.py          # ODB Lens: KPI extraction
|   +-- capsule.py           # Capsule: experiment state tracking & diff
|   +-- contracts.py         # Physics contracts validation
|   +-- report.py            # Simulation report generation
|   +-- agent.py             # Abaqus-side TCP socket agent (pure stdlib)
|   +-- gui_plugin.py        # Abaqus/CAE GUI plugin (AFX menu)
|   +-- file_ipc_plugin.py   # File-based IPC fallback plugin
|   +-- client.py            # TCP client for CLI tools
|   +-- protocol.py          # Shared line-delimited JSON protocol
|   +-- cli.py               # CLI: check, doctor, setup
+-- scripts/
|   +-- start_abaqus_mcp_pro_agent.py   # noGUI launcher (TCP)
|   +-- start_abaqus_mcp_pro_ipc.py     # noGUI launcher (file IPC)
|   +-- stop_mcp_agent.py           # Stop signal for file IPC
+-- examples/
|   +-- abaqus_cantilever_classic.py
|   +-- abaqus_tensile_bar_classic.py
|   +-- show_tensile_result_viewport.py
+-- tests/                    # Test directory
```

## Credits

Built by integrating the best features from:

- [Abaqus-Control-MCP](https://github.com/Whfkl/Abaqus-Control-MCP) -- TCP socket bridge, AST diagnostics

- [CAE-Agent-Hub](https://github.com/Cai-aa/CAE-Agent-Hub) -- High-level tools, skills, and architecture

- [abaqus-mcp](https://github.com/Cai-aa/abaqus-mcp) -- File-based IPC transport

- [Codex_MCP_Abaqus](https://github.com/Zhangyoupeng1996/Codex_MCP_Abaqus) -- noGUI mode and examples

