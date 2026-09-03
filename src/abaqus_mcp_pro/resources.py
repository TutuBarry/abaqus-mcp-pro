"""MCP resource definitions for Abaqus MCP server."""

from __future__ import annotations

from .transport import DEFAULT_HOST, DEFAULT_PORT, _socket_request, _json_string



def session_telemetry() -> str:
    """Live Abaqus/CAE session telemetry from the socket bridge."""
    try:
        return _json_string(_socket_request('ping', timeout=5.0))
    except Exception as exc:
        return _json_string({'connected': False, 'error': str(exc), 'endpoint': f'{DEFAULT_HOST}:{DEFAULT_PORT}'})



def abaqus_status() -> str:
    """Compatibility status resource."""
    return session_telemetry()



def register_resources(mcp, instructions_text: str = '') -> None:
    """Register all MCP resources.

    Args:
        mcp: An MCPServer instance.
        instructions_text: The INSTRUCTIONS string to serve as agent-instructions resource.
    """
    mcp.resource('abaqus://session-telemetry', description='Live Abaqus/CAE session telemetry from the socket bridge. Shows models, viewports, version, and connection status.')(session_telemetry)
    mcp.resource('abaqus://status', description='Compatibility status resource. Returns the same telemetry as session-telemetry.')(abaqus_status)
    if instructions_text:
        def _make_instructions_reader(t=instructions_text):
            def _reader():
                return t
            return _reader
        mcp.resource('abaqus://agent-instructions', description='Abaqus modeling instructions for MCP clients. Includes skills knowledge base reference.')(_make_instructions_reader())