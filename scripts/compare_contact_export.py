"""Abaqus Python: compare exported contact scalars node-by-node to native ODB."""
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from odbAccess import openOdb

model_path = Path(sys.argv[1])
model = json.loads(model_path.read_text(encoding='utf-8'))
odb = openOdb(model['odb_path'], readOnly=True)
try:
    step = odb.steps[model['steps'][0]['name']]
    checks = []
    for frame in model['frames']:
        root = ET.parse(model_path.parent / frame['vtu_file'])
        native = step.frames[frame['source_frame']]
        for field in model['fields']:
            if field.get('association') != 'contact': continue
            source = field['source_field']
            actual = list(map(float, root.find('.//PointData/DataArray[@Name="' + field['name'] + '"]').text.split()))
            expected = {(v.instance.name, v.nodeLabel): float(v.data) for v in native.fieldOutputs[source].values} if source in native.fieldOutputs else {}
            count = 0
            for node, value in zip(model['node_ids'], actual):
                key = (node['instance'], node['label'])
                if key in expected:
                    assert math.isclose(value, expected[key], rel_tol=1e-12, abs_tol=1e-12), (frame['frame'], source, key)
                    count += 1
                else:
                    assert math.isnan(value), 'Missing contact value became zero'
            checks.append({'frame': frame['frame'], 'field': source, 'verified_nodes': count})
    report = {'passed': bool(checks), 'checks': checks, 'model': str(model_path)}
    Path(sys.argv[2]).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('CONTACT_EXPORT_COMPARISON', report['passed'], len(checks))
finally:
    odb.close()
