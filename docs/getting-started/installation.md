# Installation

## Prerequisites

- **Python 3.10+** — Required for the MCP server
- **Abaqus 2024+** — With built-in Python 3.10
- **MCP-compatible AI client** — Codex, Claude Desktop, etc.

## Install the Package

```bash
pip install -e .
```

Or install from the repository:

```bash
pip install git+https://github.com/TutuBarry/abaqus-mcp-pro.git
```

## Install the Abaqus GUI Plugin

```bash
abaqus-mcp-pro-setup
```

This copies the GUI plugin to your Abaqus plugins directory. Alternatively, you can manually copy `src/abaqus_mcp_pro/gui_plugin.py` to `~/abaqus_plugins/`.

You can customize the plugin directory by setting the environment variable:

```bash
export ABAQUS_MCP_PLUGIN_DIR=/path/to/abaqus_plugins
```

## Verify Installation

```bash
abaqus-mcp-pro-doctor
```

This prints package version, Python version, entry point paths, and platform details.
