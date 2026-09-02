# Tools Reference

Abaqus MCP Pro provides 25 MCP tools for full Abaqus automation.

## Core Tools

| Tool | Description |
|------|-------------|
| `ping` | Check bridge connectivity + session status |
| `check_abaqus_connection` | Human-readable connection status |
| `run_python` | Execute arbitrary Python in Abaqus kernel |
| `execute_script` | Compatibility wrapper returning stdout |
| `set_workdir` | Change Abaqus working directory |

## Model Inspection

| Tool | Description |
|------|-------------|
| `get_model_info` | List parts, materials, steps, loads, BCs |
| `list_jobs` | List all jobs and their status |

## Job Management

| Tool | Description |
|------|-------------|
| `submit_job` | Submit a job and wait for completion |
| `monitor_job_status` | Tail .sta/.msg diagnostics |
| `diagnose_job` | Solver Doctor: 40+ error pattern detection |

## ODB & Post-Processing

| Tool | Description |
|------|-------------|
| `inspect_odb` | Read-only ODB: frames, variables, sections |
| `get_odb_info` | Compatibility wrapper for inspect_odb |
| `extract_kpis` | ODB Lens: extract KPI values |
| `capture_viewport` | Capture viewport as base64 image |
| `get_viewport_image` | Compatibility wrapper returning data URI |

## Experiment Tracking

| Tool | Description |
|------|-------------|
| `create_capsule` | Save experiment state snapshot |
| `list_capsules` | List all saved capsules |
| `load_capsule` | Load a saved capsule |
| `delete_capsule` | Delete a saved capsule |
| `compare_capsules` | Diff two capsules |
| `check_physics_contracts` | Validate physics contracts |
| `generate_report` | Generate simulation report |

## Model Health

| Tool | Description |
|------|-------------|
| `check_silent_failures` | Detect silent failure conditions |
| `check_model_integrity` | Quick model integrity check |
| `converge_advice` | Auto-fix suggestions for convergence |

## Abaqus API Tools

The server also exposes 50+ direct Abaqus API tools for geometry, materials, loads, BCs, steps, mesh, contact, and more. See the full list in the source code at `src/abaqus_mcp_pro/tools.py`.
