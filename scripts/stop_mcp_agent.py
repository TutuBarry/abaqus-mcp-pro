# -*- coding: utf-8 -*-
"""
Stop Abaqus MCP loop.

Run this script from any Python environment to signal the MCP plugin to stop.
Respects the ABAQUS_MCP_HOME environment variable.
"""
import os

mcp_home = os.environ.get('ABAQUS_MCP_HOME', '').strip()
if not mcp_home:
    mcp_home = os.path.join(os.path.expanduser('~'), '.abaqus-mcp-pro')

stop_file = os.path.join(mcp_home, 'stop.flag')
with open(stop_file, 'w') as f:
    f.write('stop')
print("Stop signal sent to Abaqus MCP (" + mcp_home + ")")
