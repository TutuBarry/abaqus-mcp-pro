# Client API

## AbaqusBridgeClient

The TCP client for communicating with the Abaqus-side agent.

```python
from abaqus_mcp_pro.client import AbaqusBridgeClient

client = AbaqusBridgeClient(host="127.0.0.1", port=48152, timeout=60)

# Check connectivity
status = client.ping()
print(status["models"])

# Execute Python code in Abaqus
result = client.execute("from abaqus import mdb; result = list(mdb.models.keys())")
print(result["return_value"])
```

## FileIPCClient

The file-based IPC client for fallback communication.

```python
from abaqus_mcp_pro.client import FileIPCClient

client = FileIPCClient(mcp_home="/path/to/workspace", timeout=60)
result = client.request("execute", {"code": "result = 42"})
```

## CLI Tools

### check

```bash
abaqus-mcp-pro-check --host 127.0.0.1 --port 48152
```

### doctor

```bash
abaqus-mcp-pro-doctor --verify-connection
```

### setup

```bash
abaqus-mcp-pro-setup
```
