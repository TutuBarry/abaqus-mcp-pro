# Quick Start

## 1. Start Abaqus/CAE

Launch Abaqus/CAE normally. Then activate the bridge:

**Plug-ins > ABAQUS MCP Pro > Start MCP Bridge**

You should see a confirmation message in the Abaqus message area.

## 2. Configure Your MCP Client

### Codex

```bash
codex mcp add abaqus-mcp-pro -- python_path "absolute/path/to/server.py"
```

### Claude Desktop

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "abaqus-mcp-pro": {
      "command": "abaqus-mcp-pro-server",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152"
      }
    }
  }
}
```

## 3. Verify Connection

```bash
abaqus-mcp-pro-check
```

Expected output:

```
Abaqus MCP Pro agent is reachable.
Ping:
{
  "python": "3.10.x",
  "models": ["Model-1"],
  ...
}
```

## 4. Start Using Tools

Once connected, your AI client can use all MCP tools. Try asking:

> "Show me the current model info"

The AI will call `get_model_info` and display your Abaqus model structure.
