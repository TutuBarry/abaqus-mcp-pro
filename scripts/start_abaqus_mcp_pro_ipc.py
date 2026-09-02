# -*- coding: utf-8 -*-
"""Start the ABAQUS MCP file IPC plugin inside Abaqus/CAE (noGUI mode).

Usage:
    abaqus cae noGUI=start_abaqus_mcp_pro_ipc.py

Or set environment variables:
    ABAQUS_MCP_HOME - working directory for commands/results files
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from abaqus_mcp_pro.file_ipc_plugin import mcp_loop

if __name__ == "__main__":
    mcp_loop()
