# Transport API

## Environment Variables

The transport layer is configured through environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP host |
| `ABAQUS_MCP_PORT` | `48152` | TCP port |
| `ABAQUS_MCP_TIMEOUT` | `60` | Timeout in seconds |
| `ABAQUS_MCP_TRANSPORT` | `socket` | `socket` or `file` |

## Protocol

Newline-delimited JSON protocol.

### Request

```json
{"id": "uuid", "method": "execute", "params": {"code": "..."}}
```

### Success Response

```json
{"id": "uuid", "ok": true, "result": {"return_value": ..., "stdout": "..."}}
```

### Error Response

```json
{"id": "uuid", "ok": false, "error": {"message": "...", "type": "..."}}
```

## Internal Functions

### `_bridge_request(method, params, timeout)`

Sends a request to the Abaqus bridge and returns the result. Automatically selects TCP or file IPC based on `ABAQUS_MCP_TRANSPORT`.

### `_exec(code, timeout)`

Convenience wrapper for executing Python code in Abaqus.
