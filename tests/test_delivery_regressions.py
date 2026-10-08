"""Regression tests execute generated code and data paths, not substring checks."""
import ast
import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace as NS
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from abaqus_mcp_pro import agent, capsule, protocol
from abaqus_mcp_pro.kpi_runtime import query_odb


def load_file(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = load_file('test_exporter', 'viewer/export/export_to_vtk.py')
viewer = load_file('test_viewer', 'viewer/serve_viewer.py')


@pytest.fixture
def constants(monkeypatch):
    values = NS(ELEMENT_NODAL='ELEMENT_NODAL', MISES='MISES', MAGNITUDE='MAGNITUDE')
    monkeypatch.setitem(sys.modules, 'abaqusConstants', values)
    return values


def make_odb():
    class Field:
        def __init__(self, values, labels=()):
            self.values = values
            self.componentLabels = labels
            self.validInvariants = ('MISES',) if len(labels) == 6 else ()

        def getSubset(self, *, region=None, position=None, readOnly=True):
            if isinstance(region, str):
                raise TypeError('Expected OdbSet')
            return self

        def getScalarField(self, *, componentLabel=None, invariant=None):
            values = []
            for item in self.values:
                if componentLabel:
                    data = item.data[self.componentLabels.index(componentLabel)]
                elif invariant == 'MISES':
                    data = item.mises
                else:
                    data = math.sqrt(sum(v * v for v in item.data))
                values.append(NS(data=data))
            return Field(values)

    instances = {}
    u, stress = [], []
    for name in ('ONE', 'TWO'):
        instance = NS(name=name)
        instance.nodes = [NS(label=i + 1, coordinates=point) for i, point in
                          enumerate(((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)))]
        instance.elements = [NS(type='C3D4', connectivity=(1, 2, 3, 4))]
        instance.nodeSets = {'FIXED': NS(name='FIXED')}
        instances[name] = instance
        for node in instance.nodes:
            u.append(NS(instance=instance, nodeLabel=node.label, data=(3.0 if name == 'ONE' else 6.0, 4.0, 0.0)))
            stress.append(NS(instance=instance, nodeLabel=node.label, data=(123., 0., 0., 0., 0., 0.), mises=123.))
    frame = NS(frameValue=1.0, frameId=0, fieldOutputs={
        'U': Field(u, ('U1', 'U2', 'U3')),
        'S': Field(stress, ('S11', 'S22', 'S33', 'S12', 'S13', 'S23'))})
    return NS(name='fixture.odb', steps={'Load': NS(name='Load', procedure='STATIC', frames=[frame])},
              rootAssembly=NS(instances=instances, nodeSets={}, elementSets={}), close=lambda: None)


def test_export_real_odb_shapes_and_instance_values(tmp_path, constants):
    odb = make_odb()
    path = exporter.export_odb_to_vtk('fixture.odb', str(tmp_path), fields=['U', 'S'],
                                      deformation_scale=0, _odb_handle=odb)
    model = json.loads(Path(path).read_text())
    assert model['num_nodes'] == 8
    assert model['num_elements'] == 2
    root = ET.parse(tmp_path / 'frame_0000.vtu')
    values = list(map(float, root.find('.//PointData/DataArray[@Name="U"]').text.split()))
    assert values[:3] == [3, 4, 0]
    assert values[12:15] == [6, 4, 0]
    assert set(map(float, root.find('.//PointData/DataArray[@Name="S_mises"]').text.split())) == {123}
    assert list(map(int, root.find('.//Cells/DataArray[@Name="types"]').text.split())) == [10, 10]
    assert model['node_ids'][4] == {'instance': 'TWO', 'label': 1}


def test_missing_value_is_not_zero():
    field = NS(values=[])
    assert math.isnan(exporter._read_nodal_field(field, {('ONE', 1): 0}, 1, 1)[0])


def test_kpi_api_and_invalid_selections(constants):
    odb = make_odb()
    queries = [dict(query_id='s', field='S', invariant='Mises'),
               dict(query_id='u', field='U', component='U1', region='ONE/FIXED'),
               dict(query_id='bad_step', field='U', component='U1', step='missing'),
               dict(query_id='bad_frame', field='U', component='U1', frame=55),
               dict(query_id='bad_region', field='U', component='U1', region='missing')]
    result = query_odb(odb, queries)
    assert result[0]['value'] == 123
    assert not result[1]['error']
    assert all(r['error'] and r['value'] is None for r in result[2:])


@pytest.mark.parametrize('key,value', [('step_index', 'sum([1,2])'), ('frame_step', 0),
                                     ('step_index', True), ('deformation_scale', float('nan')),
                                     ('fields', ['S', '__import__("os")'])])
def test_viewer_rejects_non_data_parameters(tmp_path, key, value):
    file = tmp_path / 'model.odb'
    file.touch()
    with pytest.raises(ValueError):
        viewer.validate_export(dict(odb_path=str(file), **{key: value}))


def test_viewer_outputs_cannot_fall_back_to_demo(tmp_path):
    handler = object.__new__(viewer.ViewerHandler)
    handler.directory = str(tmp_path / 'static')
    assert 'samples' not in handler.translate_path('/model.json')
    root = tmp_path / 'exports'
    identifier = 'a' * 32
    handler.server = NS(exports=NS(root=root, get=lambda key: {'status': 'completed'}))
    assert Path(handler.translate_path('/exports/' + identifier + '/model.json')) == root / identifier / 'model.json'
    assert '__invalid__' in handler.translate_path('/exports/' + identifier + '/parameters.json')
    assert '__invalid__' in handler.translate_path('/samples/../../secret.json')


def test_protocol_limit_includes_final_chunk():
    a, b = socket.socketpair()
    try:
        protocol.send_message(a, {'x': 'a' * 100})
        with pytest.raises(protocol.ProtocolError):
            protocol.read_message(b, max_bytes=10)
    finally:
        a.close()
        b.close()


def test_execution_does_not_reuse_old_result():
    assert agent._execute('result = 42')['return_value'] == 42
    assert agent._execute('unrelated = 7')['return_value'] is None


def test_read_blocks_until_writer_finishes():
    entered, release, read_done = threading.Event(), threading.Event(), threading.Event()
    agent._GLOBALS.update(entered=entered, release=release)
    writer = threading.Thread(target=lambda: agent._execute('entered.set(); release.wait(3)'))
    reader = threading.Thread(target=lambda: (agent._execute('result = 9', True), read_done.set()))
    writer.start()
    assert entered.wait(2)
    try:
        reader.start()
        assert not read_done.wait(0.1)
    finally:
        release.set()
        writer.join(3)
        reader.join(3)
    assert read_done.is_set()


def test_capsule_capture_in_fresh_namespace():
    code = capsule.CAPSULE_CAPTURE_CODE.replace('__CAPSULE_ID__', repr('test')).replace('__NOTES__', repr(''))
    namespace = {}
    exec(code, namespace)
    assert namespace['result']['timestamp']


def test_gui_dispatch_generated_code_is_executable(monkeypatch, tmp_path):
    from abaqus_mcp_pro.plugin_install import install_plugin
    monkeypatch.setenv('ABAQUS_MCP_PLUGIN_DIR', str(tmp_path))
    install_plugin()
    tree = ast.parse((ROOT / 'src/abaqus_mcp_pro/gui_plugin.py').read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_handle_on_gui_thread')
    def kernel(code, timeout):
        namespace = {}
        exec(code, namespace)
        return {'ok': True, 'return_value': namespace['result']}
    namespace = {'os': os, 'time': time, '__file__': str(tmp_path / 'abaqus_mcp_pro_gui_plugin.py'), '_run_kernel_code': kernel}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<gui>', 'exec'), namespace)
    item = NS(cancelled=False, deadline=time.monotonic()+5, method='odb_list', params={})
    assert namespace['_handle_on_gui_thread'](item) == {'odbs': {}}


def test_operation_id_replay_does_not_execute_twice():
    identifier = 'regression-idempotency'
    agent._REQUEST_HISTORY.pop(identifier, None)
    agent._GLOBALS['counter'] = 0
    params = {'code': 'counter += 1; result = counter', 'operation_id': identifier}
    assert agent.dispatch('execute', params)['return_value'] == 1
    assert agent.dispatch('execute', params)['return_value'] == 1
    assert agent.dispatch('request_status', {'operation_id': identifier})['status'] == 'completed'
    with pytest.raises(ValueError):
        agent.dispatch('execute', dict(params, code='result = 2'))


def test_material_table_rows(monkeypatch):
    from abaqus_mcp_pro import abaqus_tools
    calls = []
    class Material:
        def Elastic(self, **kwargs):
            pass
        def Density(self, table):
            calls.append(table)
        def Plastic(self, table):
            calls.append(table)
    monkeypatch.setitem(sys.modules, 'abaqus', NS(mdb=NS(models={'Model-1': NS(Material=lambda **kwargs: Material())}), session=NS()))
    monkeypatch.setitem(sys.modules, 'abaqusConstants', NS(__all__=[]))
    async def execute(code, timeout=None):
        return agent._execute(code)
    monkeypatch.setattr(abaqus_tools, '_run_python', execute)
    asyncio.run(abaqus_tools.create_plastic_material('Steel', 210000, .3, 250, density=7.85e-9))
    assert calls == [((250, 0.0),), ((7.85e-9,),)]


def test_quadratic_beam_export_node_order(tmp_path, constants):
    odb = make_odb()
    for instance in odb.rootAssembly.instances.values():
        instance.elements = [NS(type='B32', connectivity=(1, 2, 3))]
    exporter.export_odb_to_vtk('beam.odb', str(tmp_path), fields=['U'], deformation_scale=0, _odb_handle=odb)
    root = ET.parse(tmp_path / 'frame_0000.vtu')
    assert list(map(int, root.find('.//Cells/DataArray[@Name="connectivity"]').text.split())) == [0, 2, 1, 4, 6, 5]


def test_section_point_selection_and_missing_data(constants):
    instance = NS(name='ONE')
    values = [NS(instance=instance, nodeLabel=1, data=(value,), sectionPoint=NS(number=section))
              for value, section in [(10, 1), (90, 2)]]
    field = NS(getSubset=lambda **kwargs: NS(values=values))
    with pytest.raises(ValueError, match='Multiple section points'):
        exporter._read_elem_nodal_field(field, {('ONE', 1): 0}, 1, 1, [])
    selected = exporter._read_elem_nodal_field(field, {('ONE', 1): 0}, 1, 1, [], 2)
    assert selected['data'] == [90]


def test_submit_job_default_is_nonblocking_and_abort_is_error(monkeypatch):
    from abaqus_mcp_pro import tools
    calls = []
    job = NS(status='NONE')
    def submit(**kwargs):
        calls.append('submit')
        job.status = 'SUBMITTED'
    def wait():
        calls.append('wait')
        job.status = 'ABORTED'
    job.submit, job.waitForCompletion = submit, wait
    monkeypatch.setitem(sys.modules, 'abaqus', NS(mdb=NS(jobs={'job': job}), session=NS()))
    async def execute(code, timeout=None, operation_id=None):
        result = tools._unwrap_execution_result(agent._execute(code))
        result['operation_id'] = 'test-op'
        return result
    monkeypatch.setattr(tools, 'run_python', execute)
    result = json.loads(asyncio.run(tools.submit_job('job')))
    assert calls == ['submit'] and not result['completed']
    job.status = 'NONE'
    with pytest.raises(RuntimeError, match='ABORTED'):
        asyncio.run(tools.submit_job('job', wait=True))


def test_capsule_capture_rejects_ambiguous_jobs(monkeypatch):
    jobs = {key: NS(status='COMPLETED') for key in ('one', 'two')}
    monkeypatch.setitem(sys.modules, 'abaqus', NS(mdb=NS(models={}, jobs=jobs), session=NS()))
    code = capsule.CAPSULE_CAPTURE_CODE.replace('__CAPSULE_ID__', repr('test')).replace('__NOTES__', repr(''))
    ns = {}
    exec(code, ns)
    assert 'Multiple jobs' in ns['result']['capture_error']
    ns = {'_mcp_capsule_job_name': 'one'}
    exec(code, ns)
    assert ns['result']['job_name'] == 'one' and not ns['result'].get('capture_error')


def test_retry_can_change_timeout_without_reexecution():
    import uuid
    identifier = uuid.uuid4().hex
    params = {'code': 'result = 7', 'operation_id': identifier, 'timeout': 1}
    assert agent.dispatch('execute', params)['return_value'] == 7
    assert agent.dispatch('execute', dict(params, timeout=2))['return_value'] == 7
