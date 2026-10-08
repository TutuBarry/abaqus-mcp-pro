"""Connect completed local ODBs to an authenticated, task-specific viewer URL."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid


def session_file():
    return Path(os.environ.get('ABAQUS_VIEWER_SESSION_FILE', Path.home() / '.abaqus-mcp-pro/viewer-session.json'))


def request(session, path, payload=None):
    url = urllib.parse.urlsplit(session['url'])
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Viewer bridge requires a local HTTP service')
    req = urllib.request.Request(session['url'] + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer ' + session['token'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def ensure_viewer():
    file = session_file()
    try:
        session = json.loads(file.read_text(encoding='utf-8'))
        if request(session, '/api/health').get('viewer_protocol') == 2:
            return session
    except (OSError, ValueError, KeyError):
        pass
    file.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ABAQUS_VIEWER_HOST='127.0.0.1', ABAQUS_VIEWER_PORT='0',
               ABAQUS_VIEWER_TOKEN=secrets.token_urlsafe(32))
    source = Path(__file__).resolve().parents[2] / 'viewer/serve_viewer.py'
    command = [sys.executable, '-u', str(source)] if source.is_file() else [sys.executable, '-u', '-m', 'abaqus_mcp_pro.viewer.serve_viewer']
    with (file.parent / 'viewer.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            session = json.loads(file.read_text(encoding='utf-8'))
            if session['token'] == env['ABAQUS_VIEWER_TOKEN'] and request(session, '/api/health').get('viewer_protocol') == 2:
                return session
        except (OSError, ValueError, KeyError):
            pass
        if process.poll() is not None:
            raise RuntimeError('Viewer startup failed; inspect ' + str(file.parent / 'viewer.log'))
        time.sleep(.1)
    raise TimeoutError('Viewer startup timed out')


def publish_result(odb_path, unit_system='', timeout=600):
    path = Path(odb_path).resolve(strict=True)
    if path.suffix.lower() != '.odb':
        raise ValueError('Expected an ODB result')
    stat = path.stat()
    signature = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            signature.update(chunk)
    fingerprint = hashlib.sha256((str(path) + signature.hexdigest() + unit_system).encode()).hexdigest()
    session = ensure_viewer()
    payload = {'odb_path': str(path), 'unit_system': unit_system, 'request_id': fingerprint}
    task = request(session, '/api/export', payload)
    if task['status'] in ('failed', 'cancelled', 'interrupted'):
        payload['request_id'] = uuid.uuid4().hex
        task = request(session, '/api/export', payload)
    deadline = time.monotonic() + timeout
    while task['status'] in ('queued', 'running', 'cancelling'):
        if time.monotonic() > deadline:
            return {'status': task['status'], 'task_id': task['task_id'], 'error': 'Export still pending; poll the task'}
        time.sleep(.2)
        task = request(session, '/api/tasks/' + task['task_id'])
    if task['status'] != 'completed':
        return {'status': task['status'], 'task_id': task['task_id'], 'error': task.get('error', 'Export unavailable')}
    if (path.stat().st_size, path.stat().st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise RuntimeError('ODB changed during export; wait for the job to finish')
    return {'status': 'completed', 'task_id': task['task_id'], 'odb_path': str(path),
            'odb_sha256': signature.hexdigest(),
            'url': session['url'] + '/?task=' + task['task_id'] + '#token=' + session['token']}
