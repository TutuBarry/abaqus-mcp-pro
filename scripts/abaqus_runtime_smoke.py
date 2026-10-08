"""Run inside `abaqus cae noGUI=...` in an isolated verification directory.

Set ABAQUS_MCP_VERIFY_ODB to an existing reference ODB and
ABAQUS_MCP_VERIFY_SOURCE to the repository root. This checks actual
kernel modeling and loopback bridge requests; it does not test GUI menus.
"""
import json
import os
from pathlib import Path
import secrets
import sys
import traceback

# CAE executes noGUI scripts without defining __file__.
sys.path.insert(0, str(Path(os.environ['ABAQUS_MCP_VERIFY_SOURCE']) / 'src'))
os.environ['ABAQUS_MCP_TOKEN'] = secrets.token_hex(24)
from abaqus_mcp_pro import agent
from abaqus_mcp_pro.client import AbaqusBridgeClient


def main():
    report = {'python': sys.version, 'checks': []}
    server = None
    def check(name, action):
        try:
            value = action()
            if isinstance(value, dict) and value.get('ok') is False:
                raise RuntimeError(str(value))
            report['checks'].append({'name': name, 'status': 'passed', 'result': value})
            return value
        except Exception as exc:
            report['checks'].append({'name': name, 'status': 'failed', 'error': str(exc),
                                     'traceback': traceback.format_exc()})
            return None
    try:
        check('kernel_geometry_material_mesh', lambda: agent.dispatch('execute', {'code': '''
from abaqus import mdb
from abaqusConstants import *
model = mdb.Model(name='MCP_Verification')
sketch = model.ConstrainedSketch(name='profile', sheetSize=20.0)
sketch.rectangle(point1=(0.0, 0.0), point2=(10.0, 1.0))
part = model.Part(name='Block', dimensionality=THREE_D, type=DEFORMABLE_BODY)
part.BaseSolidExtrude(sketch=sketch, depth=1.0)
material = model.Material(name='Steel')
material.Elastic(table=((210000.0, 0.3),))
material.Density(table=((7.85e-9,),))
material.Plastic(table=((250.0, 0.0),))
model.HomogeneousSolidSection(name='Section', material='Steel')
part.SectionAssignment(region=part.Set(name='Body', cells=part.cells), sectionName='Section')
part.seedPart(size=0.5)
part.generateMesh()
model.rootAssembly.Instance(name='Block-1', part=part, dependent=ON)
model.StaticStep(name='Load', previous='Initial')
assert len(part.nodes) > 0 and len(part.elements) > 0
result = {'nodes':len(part.nodes), 'elements':len(part.elements), 'materials':list(model.materials.keys())}
'''}))
        server = agent.start_background('127.0.0.1', 0)
        client = AbaqusBridgeClient(port=server.server_address[1], timeout=20)
        check('socket_ping', client.ping)
        check('socket_capabilities', lambda: client.request('capabilities'))
        check('socket_mdb_info', lambda: client.request('mdb_info'))
        opened = check('socket_odb_open', lambda: client.request('odb_open', {'path': os.environ['ABAQUS_MCP_VERIFY_ODB']}))
        if opened:
            handle = opened['handle']
            check('socket_odb_summary', lambda: client.request('odb_summary', {'handle': handle}))
            for field in ('S', 'U'):
                check('socket_extract_' + field, lambda field=field: client.request('extract_field', {'handle': handle, 'field_name': field}))
            check('socket_odb_close', lambda: client.request('odb_close', {'handle': handle}))
        check('socket_execute', lambda: client.execute('result = 6 * 7'))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        report['status'] = 'passed' if report['checks'] and all(c['status'] == 'passed' for c in report['checks']) else 'failed'
        Path('runtime-validation.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        print('MCP_RUNTIME_VALIDATION=' + report['status'])


if __name__ == '__main__':
    main()
