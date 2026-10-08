"""Fixed Abaqus subprocess entrypoint; reads JSON parameters as data."""
import json
import sys
from pathlib import Path
from export_to_vtk import export_odb_to_vtk

if __name__ == '__main__':
    parameters = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    export_odb_to_vtk(**parameters)
