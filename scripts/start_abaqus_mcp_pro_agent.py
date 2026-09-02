# -*- coding: utf-8 -*-
"""Start the ABAQUS MCP TCP socket agent inside Abaqus/CAE (noGUI mode).

Usage:
    abaqus cae noGUI=start_abaqus_mcp_pro_agent.py

Or set environment variables:
    ABAQUS_MCP_HOST=127.0.0.1
    ABAQUS_MCP_PORT=48152
"""

import os
import sys

# Add the source directory to the path so we can import abaqus_mcp_pro.agent
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from abaqus_mcp_pro.agent import main

if __name__ == "__main__":
    main()
