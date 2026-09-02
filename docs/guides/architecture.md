# Architecture

## Overview

```
MCP Client (Codex/Claude)
    |
    v  stdio
MCP Server (server.py)
    |
    v  TCP socket (localhost:48152)
Abaqus GUI Plugin (gui_plugin.py / agent.py)
    |
    v  Abaqus Python API
Abaqus/CAE Kernel
```

## Components

### MCP Server (`server.py`)

The stdio-based MCP server that registers all tools, prompts, and resources. It communicates with the Abaqus-side agent through a TCP socket.

### Abaqus Agent (`agent.py`)

A pure-Python (stdlib only) TCP socket server that runs inside the Abaqus/CAE kernel. It receives JSON-RPC-style requests and executes Python code in the Abaqus namespace.

### GUI Plugin (`gui_plugin.py`)

An Abaqus/CAE AFX plugin that provides menu items to start/stop the TCP bridge from within the Abaqus GUI.

### File IPC Plugin (`file_ipc_plugin.py`)

A fallback transport that uses file-based command/result exchange when TCP is unavailable.

### Transport Layer (`transport.py`)

Manages the communication between the MCP server and the Abaqus agent. Supports both TCP socket and file IPC modes.

## Protocol

The wire protocol is newline-delimited JSON. Each message is a single JSON object followed by a newline character.

Request format:
```json
{"id": "uuid", "method": "execute", "params": {"code": "..."}}
```

Response format:
```json
{"id": "uuid", "ok": true, "result": {"return_value": ..., "stdout": "..."}}
```
