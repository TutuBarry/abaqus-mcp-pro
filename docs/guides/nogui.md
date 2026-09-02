# noGUI Mode

Run Abaqus in batch mode without the GUI — ideal for headless servers and CI/CD pipelines.

## TCP Agent

```bash
abaqus cae noGUI=scripts/start_abaqus_mcp_pro_agent.py
```

This starts the full TCP socket agent inside Abaqus, using the same protocol as the GUI plugin.

## File IPC

```bash
abaqus cae noGUI=scripts/start_abaqus_mcp_pro_ipc.py
```

Uses file-based command/result exchange. Set `ABAQUS_MCP_TRANSPORT=file` in your MCP client configuration.

## noGUI Server

```bash
abaqus cae noGUI=scripts/nogui_server.py -- --port 48152
```

A standalone server implementation with a subset of tools. Supports `--port` and `--host` arguments.

## Environment Variables

All standard environment variables apply in noGUI mode:

- `ABAQUS_MCP_HOST` — TCP host (default: `127.0.0.1`)
- `ABAQUS_MCP_PORT` — TCP port (default: `48152`)
- `ABAQUS_MCP_HOME` — Working directory for file IPC
