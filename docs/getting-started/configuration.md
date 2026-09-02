# Configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP host for the bridge |
| `ABAQUS_MCP_PORT` | `48152` | TCP port for the bridge |
| `ABAQUS_MCP_TIMEOUT` | `60` | Socket timeout in seconds |
| `ABAQUS_MCP_MAX_MESSAGE_BYTES` | `33554432` | Max message size (32 MB) |
| `ABAQUS_MCP_PLUGIN_DIR` | `~/abaqus_plugins` | Plugin install directory |
| `ABAQUS_MCP_HOME` | auto-detect | Working directory for file IPC |
| `ABAQUS_MCP_TRANSPORT` | `socket` | Transport mode: `socket` or `file` |

## Transport Modes

### TCP Socket (Default)

The recommended mode. Uses a local TCP socket on `127.0.0.1:48152` for low-latency communication.

### File IPC (Fallback)

Uses file-based commands/results exchange. Set `ABAQUS_MCP_TRANSPORT=file` to enable. Useful when TCP is not available in restricted environments.

## MCP Client Configuration

### Codex

The Codex MCP configuration is managed through `codex mcp` commands. Use `codex mcp list` to verify the server is registered.

### Claude Desktop

Configuration is stored in `~/.claude.json` under `mcpServers`. Restart Claude after adding the server.
