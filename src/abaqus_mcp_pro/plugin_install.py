"""Install the self-contained standard-library bridge runtime alongside the GUI plugin."""
from importlib import resources
import os
import time
from pathlib import Path


def install_plugin():
    target = Path(os.environ.get('ABAQUS_MCP_PLUGIN_DIR', Path.home() / 'abaqus_plugins'))
    runtime = target / 'abaqus_mcp_pro_runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    files = resources.files('abaqus_mcp_pro')
    destinations = {'gui_plugin.py': target / 'abaqus_mcp_pro_gui_plugin.py'}
    destinations.update({name: runtime / name for name in ('__init__.py', 'agent.py', 'protocol.py')})
    for name, destination in destinations.items():
        content = files.joinpath(name).read_bytes()
        if not destination.exists() or destination.read_bytes() != content:
            tmp = destination.with_suffix('.tmp')
            tmp.write_bytes(content)
            os.replace(tmp, destination)
    # Older releases used this filename and register the same AFX menu twice.
    # Preserve recognizable legacy code as a non-plugin backup; never remove it.
    legacy = target / 'abaqus_mcp_gui_plugin.py'
    if legacy.is_file():
        content = legacy.read_text(encoding='utf-8', errors='replace')
        if 'ABAQUS MCP Pro|Start MCP Bridge' in content and 'def start_gui_agent(' in content:
            backup = legacy.with_name(legacy.name + '.disabled-' + str(time.time_ns()))
            legacy.rename(backup)
    return destinations['gui_plugin.py']
