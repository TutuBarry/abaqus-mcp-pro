# -*- coding: utf-8 -*-
"""MCP helper: runs VTU export inside Abaqus Python."""
from __future__ import print_function
import json, os, sys

# VIEWER_DIR and ODB_PATH etc. are replaced by the MCP tool
sys.path.insert(0, r'__VIEWER_DIR__')
from export.export_to_vtk import export_odb_to_vtk

output_dir = r'__OUTPUT_DIR__' if r'__OUTPUT_DIR__' else (os.path.splitext(r'__ODB_PATH__')[0] + '_vtk')
fields_list = [f.strip() for f in '__FIELDS__'.split(',') if f.strip()]

result = export_odb_to_vtk(
    odb_path=r'__ODB_PATH__',
    output_dir=output_dir,
    step_index=__STEP_IDX__,
    frame_step=__FRAME_STEP__,
    deformation_scale=__DEF_SCALE__,
    fields=fields_list,
    binary=False,
)
if result:
    md = json.loads(open(result).read())
    out = {
        'ok': True,
        'output_dir': output_dir,
        'model_json_path': result,
        'format_version': '3.0',
        'node_count': md.get('num_nodes', 0),
        'elem_count': md.get('num_elements', 0),
        'frame_count': len(md.get('frames', [])),
    }
    print('RESULT:' + json.dumps(out))
else:
    print('RESULT:' + json.dumps({'ok': False, 'error': 'Export returned no result'}))
