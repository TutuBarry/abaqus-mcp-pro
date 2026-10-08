"""Locate Abaqus without requiring the current process to refresh its PATH."""
import os
from pathlib import Path
import shutil


def find_abaqus_command():
    configured = os.environ.get('ABAQUS_COMMAND', '').strip()
    if configured:
        return configured
    found = shutil.which('abaqus')
    if found:
        return found
    if os.name == 'nt':
        # The installer commonly uses Program Files; a running MCP client can
        # still hold the pre-installation PATH until it is restarted.
        roots = [Path(os.environ.get('ProgramFiles', 'C:/Program Files'))]
        roots += [Path(drive + folder) for drive in ('C:', 'D:', 'E:')
                  for folder in ('/Program Files', '/')]
        candidates = [root / 'SIMULIA/Commands/abaqus.bat' for root in roots]
    else:
        candidates = [Path('/usr/local/bin/abaqus'), Path('/opt/abaqus/Commands/abaqus')]
    return next((str(p) for p in candidates if p.is_file()), 'abaqus')
