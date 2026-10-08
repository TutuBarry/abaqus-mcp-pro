import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import xml.etree.ElementTree as ET

from test_delivery_regressions import exporter, make_odb, constants


def test_contact_pairs_remain_separate_and_missing_values_are_nan(tmp_path, constants):
    odb = make_odb()
    frame = odb.steps['Load'].frames[0]
    inst = odb.rootAssembly.instances['ONE']
    for name, pressure in [('CPRESS   A/B', 10), ('CPRESS   C/D', 20)]:
        frame.fieldOutputs[name] = NS(values=[NS(instance=inst, nodeLabel=1, data=float(pressure))], componentLabels=())
    output = exporter.export_odb_to_vtk('fixture.odb', str(tmp_path), fields=['CPRESS', 'COPEN'],
        deformation_scale=0, unit_system='N-mm-s-tonne', _odb_handle=odb)
    model = json.loads(Path(output).read_text())
    assert len(model['fields']) == 2
    assert model['missing_requested_fields'] == ['COPEN']
    assert all(f['unit'] == 'MPa' and f['association'] == 'contact' for f in model['fields'])
    root = ET.parse(tmp_path / 'frame_0000.vtu')
    for field, expected in zip(model['fields'], [10, 20]):
        values = list(map(float, root.find('.//DataArray[@Name="' + field['name'] + '"]').text.split()))
        assert values[0] == expected
        assert all(math.isnan(v) for v in values[1:])
    assert len(model['bodies']) == 2


def test_declared_units_only(tmp_path, constants):
    for units, expected in [('', ''), ('N-mm-s-tonne', 'MPa'), ('N-m-s-kg', 'Pa')]:
        path = exporter.export_odb_to_vtk('fixture.odb', str(tmp_path), fields=['S'],
            deformation_scale=0, unit_system=units, _odb_handle=make_odb())
        assert all(f['unit'] == expected for f in json.loads(Path(path).read_text())['fields'])


def test_viewer_bridge_rejects_remote_session():
    from abaqus_mcp_pro.viewer_bridge import request
    import pytest
    with pytest.raises(ValueError, match='local HTTP'):
        request({'url': 'https://example.com', 'token': 'not-sent'}, '/api/health')


def test_failed_export_is_not_reported_as_viewable(tmp_path, monkeypatch):
    from abaqus_mcp_pro import viewer_bridge as bridge
    file = tmp_path / 'result.odb'
    file.write_bytes(b'fixture')
    monkeypatch.setattr(bridge, 'ensure_viewer', lambda: {'url': 'http://127.0.0.1:1', 'token': 'test'})
    monkeypatch.setattr(bridge, 'request', lambda *a: {'status': 'failed', 'task_id': 'a'*32, 'error': 'no field'})
    result = bridge.publish_result(file)
    assert result['status'] == 'failed' and 'url' not in result


def test_changed_odb_uses_new_export_identity(tmp_path, monkeypatch):
    from abaqus_mcp_pro import viewer_bridge as bridge
    file = tmp_path / 'result.odb'
    file.write_bytes(b'first')
    requests = []
    monkeypatch.setattr(bridge, 'ensure_viewer', lambda: {'url': 'http://127.0.0.1:1', 'token': 'test'})
    def submit(session, path, payload):
        requests.append(payload['request_id'])
        return {'status': 'completed', 'task_id': payload['request_id'][:32]}
    monkeypatch.setattr(bridge, 'request', submit)
    first = bridge.publish_result(file)
    file.write_bytes(b'other')
    second = bridge.publish_result(file)
    assert requests[0] != requests[1]
    assert first['url'] != second['url']


def test_nogui_input_inside_spaced_directory_uses_relative_argument(tmp_path, monkeypatch):
    import asyncio
    from abaqus_mcp_pro import nogui
    directory = tmp_path / 'project with spaces'
    directory.mkdir()
    inp = directory / 'analysis.inp'
    inp.write_text('*HEADING\nfixture\n')
    def run(args, timeout, cwd):
        assert 'input=analysis.inp' in args
        assert Path(cwd) == directory
        return {'ok': False, 'error': 'fixture does not run a solver'}
    monkeypatch.setattr(nogui, '_run_abaqus_subprocess', run)
    assert not asyncio.run(nogui.submit_job_no_gui(str(inp)))['ok']


def test_nogui_completed_job_publishes_exact_odb(tmp_path, monkeypatch):
    import asyncio
    from abaqus_mcp_pro import nogui, viewer_bridge
    inp = tmp_path / 'analysis.inp'
    inp.write_text('*HEADING\nfixture\n')
    odb = tmp_path / 'analysis.odb'
    odb.write_bytes(b'fixture')
    monkeypatch.setattr(nogui, '_run_abaqus_subprocess', lambda *a: {'ok': True})
    async def status(*args): return {'status': 'completed'}
    monkeypatch.setattr(nogui, 'check_job_status', status)
    def publish(path, units):
        assert Path(path) == odb and units == 'N-mm-s-tonne'
        return {'status': 'completed', 'url': 'http://127.0.0.1:1/?task=fixture'}
    monkeypatch.setattr(viewer_bridge, 'publish_result', publish)
    result = asyncio.run(nogui.submit_job_no_gui(str(inp), unit_system='N-mm-s-tonne'))
    assert result['ok'] and result['viewer']['status'] == 'completed'
