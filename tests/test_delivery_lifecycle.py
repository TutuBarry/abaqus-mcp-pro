"""Exercise real local HTTP, file protocol, and reproducible run orchestration.

Solver-shaped fixtures validate orchestration only; they are not Abaqus results.
"""
import http.client
import json
from pathlib import Path
import sys
import threading
import time
import uuid

import pytest

from test_delivery_regressions import load_file, viewer
from abaqus_mcp_pro import workflow
from abaqus_mcp_pro.contracts import check_contracts

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'examples/verification/suite.json'


def test_reference_suite_preparation_and_portable_replay(tmp_path):
    root, record = workflow.run_manifest(SUITE, tmp_path)
    assert len(record['cases']) == 6
    assert record['status'] == 'not_verified'
    assert all(c['status'] == 'prepared' for c in record['cases'])
    replay_root, replay = workflow.run_manifest(root / 'manifest.json', tmp_path)
    assert [c['input_sha256'] for c in replay['cases']] == [c['input_sha256'] for c in record['cases']]
    assert (replay_root / 'report.md').is_file()


def test_missing_solver_cannot_pass(tmp_path):
    root, record = workflow.run_manifest(SUITE, tmp_path, True, 'missing_abaqus_' + uuid.uuid4().hex)
    assert record['status'] == 'not_verified'
    assert all(c['status'] == 'solver_unavailable' and c['contracts'] is None for c in record['cases'])
    assert (root / 'run.json').is_file()


def test_workflow_extract_error_cannot_pass(tmp_path, monkeypatch):
    def fake_process(command, cwd, log_file, timeout):
        if 'python' in command:
            (cwd / 'kpis.json').write_text(json.dumps({'error_count': 1, 'results': []}))
        else:
            (cwd / 'analysis.sta').write_text('THE ANALYSIS HAS COMPLETED SUCCESSFULLY')
            (cwd / 'analysis.odb').write_bytes(b'Fixture only')
        return 0
    monkeypatch.setattr(workflow, 'run_process', fake_process)
    _, record = workflow.run_manifest(SUITE, tmp_path, True, sys.executable)
    assert all(c['status'] == 'failed' for c in record['cases'])
    assert record['status'] == 'not_verified'


def test_workflow_numeric_contracts_and_provenance(tmp_path, monkeypatch):
    manifest = workflow.validate_manifest(SUITE)
    def fake_process(command, cwd, log_file, timeout):
        if 'python' in command:
            case = next(c for c in manifest['cases'] if c['id'] == cwd.name)
            values = {c['kpi_name']: c['expected'] for c in case['contracts']}
            extracted = {'error_count': 0, 'results': [{'query_id': k, 'value': v} for k, v in values.items()]}
            (cwd / 'kpis.json').write_text(json.dumps(extracted))
        else:
            (cwd / 'analysis.sta').write_text('THE ANALYSIS HAS COMPLETED SUCCESSFULLY')
            (cwd / 'analysis.odb').write_bytes(b'Fixture only')
        return 0
    monkeypatch.setattr(workflow, 'run_process', fake_process)
    _, record = workflow.run_manifest(SUITE, tmp_path, True, sys.executable)
    assert record['status'] == 'passed'
    assert all(len(c['odb_sha256']) == 64 for c in record['cases'])
    for case in manifest['cases']:
        rule = case['contracts'][0]
        bad = rule['expected'] + max(rule['tolerance'] * 2, 1)
        assert check_contracts([rule], {rule['kpi_name']: bad}).failed_count == 1


def test_file_protocol_auth_expiry_capture_and_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv('ABAQUS_MCP_HOME', str(tmp_path))
    monkeypatch.setenv('ABAQUS_MCP_TOKEN', 'test-token')
    plugin = load_file('delivery_file_plugin', 'src/abaqus_mcp_pro/file_ipc_plugin.py')
    command = {'id': uuid.uuid4().hex, 'type': 'execute_script', 'script': 'result = 42',
               'params': {'operation_id': uuid.uuid4().hex}}
    assert plugin.process_command(command)['success'] is False
    monkeypatch.setenv('ABAQUS_MCP_READ_ONLY', '1')
    assert plugin.process_command({'id': 'read-only', 'type': 'submit_job', 'token': 'test-token'})['success'] is False
    monkeypatch.delenv('ABAQUS_MCP_READ_ONLY')
    command['token'] = 'test-token'
    command['expires_at'] = time.time() - 1
    assert plugin.process_command(command)['success'] is False
    command['expires_at'] = time.time() + 60
    result = plugin.process_command(command)
    assert result['success'] and result['data']['return_value'] == 42
    command['id'] = uuid.uuid4().hex
    command['script'] = 'result = 43'
    assert plugin.process_command(command)['success'] is False


def test_viewer_http_auth_cookie_origin_and_output_identity(tmp_path, monkeypatch):
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'index.html').write_text('fixture viewer')
    monkeypatch.setattr(viewer, 'STATIC_DIR', static)
    manager = viewer.ExportManager(tmp_path / 'exports')
    server = viewer.http.server.ThreadingHTTPServer(('127.0.0.1', 0), viewer.ViewerHandler)
    server.token, server.exports = 'session-token', manager
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
    def request(method, path, body=None, headers=None):
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    try:
        assert request('GET', '/api/tasks/missing')[0] == 401
        assert request('GET', '/api/tasks')[0] == 401
        assert request('GET', '/api/diagnostics/missing')[0] == 401
        assert request('GET', '/', headers={'Host': 'evil.example'})[0] == 403
        headers = {'Authorization': 'Bearer session-token', 'Content-Type': 'application/json'}
        assert request('POST', '/api/session', '{}', dict(headers, Origin='https://evil.example'))[0] == 403
        status, response_headers, _ = request('POST', '/api/session', '{}', headers)
        assert status == 200 and 'HttpOnly' in response_headers['Set-Cookie']
        cookie = {'Cookie': response_headers['Set-Cookie'].split(';')[0]}
        assert json.loads(request('GET', '/api/tasks', headers=cookie)[2]) == {'tasks': []}
        assert request('GET', '/api/diagnostics/missing', headers=cookie)[0] == 404
        assert request('GET', '/api/tasks/missing', headers=cookie)[0] == 404
        assert request('GET', '/model.json', headers=cookie)[0] == 404
        identifier = 'a' * 32
        output = manager.root / identifier
        output.mkdir()
        (output / 'model.json').write_text('{"identity":"exported"}')
        manager.tasks[identifier] = {'task_id': identifier, 'status': 'completed'}
        status, _, body = request('GET', '/exports/' + identifier + '/model.json', headers=cookie)
        assert status == 200 and json.loads(body)['identity'] == 'exported'
        assert request('GET', '/exports/' + identifier + '/parameters.json', headers=cookie)[0] == 404
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(5)
        manager.close()


def test_export_deduplication_cancel_and_restart(tmp_path, monkeypatch):
    manager = viewer.ExportManager(tmp_path)
    monkeypatch.setattr(manager.pool, 'submit', lambda *args: None)
    try:
        first = manager.submit({'odb_path': 'fixture.odb'}, 'same-request')
        second = manager.submit({'odb_path': 'fixture.odb'}, 'same-request')
        assert first['task_id'] == second['task_id']
        with pytest.raises(ValueError):
            manager.submit({'odb_path': 'different.odb'}, 'same-request')
        assert manager.cancel(first['task_id'])['status'] == 'cancelled'
        running = manager.submit({'odb_path': 'other.odb'}, 'restart-request')
        restarted = viewer.ExportManager(tmp_path)
        try:
            assert restarted.get(running['task_id'])['status'] == 'interrupted'
        finally:
            restarted.close()
    finally:
        manager.close()


def test_nonfinite_kpi_never_passes_contracts():
    for value in (float('nan'), float('inf'), float('-inf')):
        report = check_contracts([{'contract_id': 'x', 'kpi_name': 'x', 'contract_type': 'exact',
                                   'expected': 0, 'tolerance': .1}], {'x': value})
        assert report.failed_count == 1


def test_nogui_subprocess_output_and_timeout(tmp_path, monkeypatch):
    from abaqus_mcp_pro import nogui
    monkeypatch.setattr(nogui, 'ABAQUS_COMMAND', sys.executable)
    result = nogui._run_abaqus_subprocess(['-c', 'print(42)'], 5, str(tmp_path))
    assert result['ok'] and result['stdout'].strip() == '42'
    result = nogui._run_abaqus_subprocess(['-c', 'import time; time.sleep(10)'], .05, str(tmp_path))
    assert not result['ok'] and 'timed out' in result['error']
