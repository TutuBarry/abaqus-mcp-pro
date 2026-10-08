"""Authenticated local viewer: fixed export script, isolated output URLs and observable jobs."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
import hashlib
import hmac
import http.server
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
import uuid
from abaqus_mcp_pro.commands import find_abaqus_command

VIEWER_DIR = Path(__file__).resolve().parent
STATIC_DIR = VIEWER_DIR / 'dist'
SAMPLES_DIR = VIEWER_DIR / 'samples'
HOST = os.environ.get('ABAQUS_VIEWER_HOST', '127.0.0.1')
PORT = int(os.environ.get('ABAQUS_VIEWER_PORT', '8080'))
MAX_BODY = 65536


def validate_export(data):
    if not isinstance(data, dict):
        raise ValueError('Request must be a JSON object')
    path = data.get('odb_path')
    if not isinstance(path, str) or not path.strip():
        raise ValueError('odb_path is required')
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != '.odb':
        raise ValueError('odb_path must be an existing .odb file')
    allowed = os.environ.get('ABAQUS_VIEWER_ODB_ROOT')
    if allowed and not path.is_relative_to(Path(allowed).resolve()):
        raise ValueError('ODB is outside ABAQUS_VIEWER_ODB_ROOT')
    params = {'odb_path': str(path)}
    for key, default in [('step_index', -1), ('frame_step', 1)]:
        value = data.get(key, default)
        if type(value) is not int or (key == 'frame_step' and value < 1):
            raise ValueError(key + ' must be a valid integer')
        params[key] = value
    scale = data.get('deformation_scale', 1.0)
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale < 0:
        raise ValueError('deformation_scale must be finite and nonnegative')
    params['deformation_scale'] = scale
    fields = data.get('fields', ['S', 'U', 'PEEQ', 'RF', 'CPRESS', 'COPEN', 'CSHEAR1', 'CSHEAR2', 'CSLIP1', 'CSLIP2'])
    if not isinstance(fields, list) or not 1 <= len(fields) <= 100:
        raise ValueError('fields must be a nonempty list of at most 100 names')
    if any(not isinstance(f, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', f) for f in fields):
        raise ValueError('Invalid field name')
    params['fields'] = list(dict.fromkeys(fields))
    units = data.get('unit_system', '')
    if units not in ('', 'N-mm-s-tonne', 'N-m-s-kg'):
        raise ValueError('Unsupported declared unit system')
    params['unit_system'] = units
    section = data.get('section_point')
    if section is not None:
        if type(section) is not int or section < 1:
            raise ValueError('section_point must be a positive integer')
        params['section_point'] = section
    return params


class ExportManager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.tasks = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='odb-export')
        for file in self.root.glob('*/task.json'):
            try:
                task = json.loads(file.read_text(encoding='utf-8'))
                if task['status'] in ('queued', 'running', 'cancelling'):
                    task.update(status='interrupted', error='Server restarted; inspect output before retrying')
                self.tasks[task['task_id']] = task
            except (OSError, ValueError, KeyError):
                continue

    def save(self, task):
        directory = self.root / task['task_id']
        directory.mkdir(exist_ok=True)
        temp = directory / 'task.tmp'
        temp.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, directory / 'task.json')

    def get(self, task_id):
        with self.lock:
            return dict(self.tasks[task_id])

    def history(self, limit=100):
        with self.lock:
            return [dict(t) for t in sorted(self.tasks.values(),
                    key=lambda t: t.get('created_at', 0), reverse=True)[:limit]]

    def diagnostics(self, task_id):
        task = self.get(task_id)
        path = self.root / task['task_id'] / 'export.log'
        tail = ''
        if path.is_file():
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 16384))
                tail = stream.read(16384).decode('utf-8', errors='replace')
        return {'task': task, 'log_tail': tail,
                'next_action': '检查 ODB 路径、Abaqus 许可和下方日志；修复后重新导出。'
                if task['status'] in ('failed', 'interrupted') else ''}

    def submit(self, params, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', request_id):
            raise ValueError('A stable request_id of 8-80 safe characters is required')
        fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        with self.lock:
            for task in self.tasks.values():
                if task['request_id'] == request_id:
                    if task['fingerprint'] != fingerprint:
                        raise ValueError('request_id already used with different parameters')
                    return dict(task)
            if sum(t['status'] in ('queued', 'running', 'cancelling') for t in self.tasks.values()) >= 8:
                raise ValueError('Export queue is full')
            task_id = uuid.uuid4().hex
            task = {'task_id': task_id, 'request_id': request_id, 'fingerprint': fingerprint,
                    'status': 'queued', 'created_at': time.time(), 'params': params,
                    'output_url': '/exports/' + task_id + '/model.json'}
            self.tasks[task_id] = task
            self.save(task)
            self.pool.submit(self.run, task_id)
            return dict(task)

    def cancel(self, task_id):
        with self.lock:
            task = self.tasks[task_id]
            if task['status'] in ('queued', 'running'):
                task['status'] = 'cancelled' if task['status'] == 'queued' else 'cancelling'
                self.save(task)
            return dict(task)

    def run(self, task_id):
        with self.lock:
            task = self.tasks[task_id]
            if task['status'] == 'cancelled':
                return
            task.update(status='running', started_at=time.time())
            self.save(task)
        directory = self.root / task_id
        try:
            params_file = directory / 'parameters.json'
            params_file.write_text(json.dumps(dict(task['params'], output_dir=str(directory))), encoding='utf-8')
            command = [find_abaqus_command(), 'python',
                       str(VIEWER_DIR / 'export/run_export.py'), str(params_file)]
            with (directory / 'export.log').open('w', encoding='utf-8') as log:
                proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=os.name != 'nt')
                deadline = time.monotonic() + 600
                while proc.poll() is None:
                    with self.lock:
                        cancelled = task['status'] == 'cancelling'
                    if cancelled or time.monotonic() > deadline:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
                        else:
                            import signal
                            os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=10)
                        raise RuntimeError('Cancelled' if cancelled else 'Export timed out')
                    time.sleep(0.1)
                if proc.returncode:
                    raise RuntimeError('Export failed; inspect export.log in the output directory')
            model = json.loads((directory / 'model.json').read_text(encoding='utf-8'))
            if not model.get('frames'):
                raise ValueError('Export produced no frames')
            for frame in model['frames']:
                file = (directory / frame['vtu_file']).resolve()
                if not file.is_relative_to(directory) or not file.is_file():
                    raise ValueError('Export has a missing or invalid frame')
            with self.lock:
                if task['status'] == 'cancelling':
                    task['status'] = 'cancelled'
                else:
                    task.update(status='completed', node_count=model['num_nodes'],
                                elem_count=model['num_elements'], frame_count=len(model['frames']))
        except Exception as exc:
            with self.lock:
                task.update(status='cancelled' if task['status'] == 'cancelling' else 'failed', error=str(exc))
        finally:
            with self.lock:
                task['finished_at'] = time.time()
                self.save(task)

    def close(self):
        with self.lock:
            for key in self.tasks:
                self.cancel(key)
        self.pool.shutdown(wait=True, cancel_futures=True)


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def is_entry_page(self):
        path = urllib.parse.urlsplit(self.path).path
        return path.endswith('/') or path.endswith('.html')

    def send_head(self):
        if self.is_entry_page():
            # Always send the current entry point after rebuilding the frontend.
            if 'If-Modified-Since' in self.headers:
                del self.headers['If-Modified-Since']
        return super().send_head()

    def end_headers(self):
        if self.is_entry_page():
            self.send_header('Cache-Control', 'no-store, max-age=0')
        super().end_headers()

    def trusted(self):
        port = self.server.server_address[1]
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'{self.server.server_address[0]}:{port}'}
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        return host in hosts and (not origin or origin == 'http://' + host)

    def authenticated(self):
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        if not token:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
                token = cookie['abaqus_viewer'].value if 'abaqus_viewer' in cookie else ''
            except Exception:
                token = ''
        return bool(token) and hmac.compare_digest(token, self.server.token)

    def respond(self, data, status=200, cookie=False):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if cookie:
            self.send_header('Set-Cookie', 'abaqus_viewer=' + self.server.token + '; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path):
        path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        missing = str(STATIC_DIR / '__invalid__')
        if path.startswith('/exports/'):
            parts = path.strip('/').split('/')
            if len(parts) != 3 or not re.fullmatch('[0-9a-f]{32}', parts[1]):
                return missing
            if parts[2] != 'model.json' and not re.fullmatch(r'frame_\d+\.vtu', parts[2]):
                return missing
            try:
                if self.server.exports.get(parts[1])['status'] != 'completed':
                    return missing
            except KeyError:
                return missing
            root = self.server.exports.root / parts[1]
            file = (root / parts[2]).resolve()
            return str(file) if file.is_relative_to(root) else missing
        if path.startswith('/samples/'):
            file = (SAMPLES_DIR / path[len('/samples/'):]).resolve()
            return str(file) if file.is_relative_to(SAMPLES_DIR) else missing
        return super().translate_path(path)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if not self.trusted():
            return self.respond({'error': 'Untrusted origin or host'}, 403)
        if path.startswith(('/api/', '/exports/')) and not self.authenticated():
            return self.respond({'error': 'Open the session URL printed by the viewer server'}, 401)
        if path.startswith('/api/tasks/'):
            try:
                return self.respond(self.server.exports.get(path.rsplit('/', 1)[-1]))
            except KeyError:
                return self.respond({'error': 'Unknown task'}, 404)
        if path == '/api/tasks':
            return self.respond({'tasks': self.server.exports.history()})
        if path.startswith('/api/diagnostics/'):
            try:
                return self.respond(self.server.exports.diagnostics(path.rsplit('/', 1)[-1]))
            except KeyError:
                return self.respond({'error': 'Unknown task'}, 404)
        if path == '/api/health':
            return self.respond({'viewer_protocol': 2})
        return super().do_GET()

    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        if not self.trusted() or (path.startswith(('/api/', '/exports/')) and not self.authenticated()):
            self.send_error(403)
            return
        super().do_HEAD()

    def do_POST(self):
        if not self.trusted() or not self.authenticated():
            return self.respond({'error': 'Authentication and same origin required'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Invalid request length')
            data = json.loads(self.rfile.read(length))
            path = urllib.parse.urlsplit(self.path).path
            if path == '/api/session':
                return self.respond({'ok': True}, cookie=True)
            if path == '/api/export':
                params = validate_export(data)
                return self.respond(self.server.exports.submit(params, data.get('request_id', '')), 202)
            if path.startswith('/api/cancel/'):
                return self.respond(self.server.exports.cancel(path.rsplit('/', 1)[-1]))
            return self.respond({'error': 'Not found'}, 404)
        except KeyError:
            return self.respond({'error': 'Unknown task'}, 404)
        except (ValueError, OSError, TypeError) as exc:
            return self.respond({'error': str(exc)}, 400)

    def do_OPTIONS(self):
        self.send_error(405, 'Cross-origin requests are not supported')

    def list_directory(self, path):
        self.send_error(404)
        return None


def main():
    token = os.environ.get('ABAQUS_VIEWER_TOKEN') or secrets.token_urlsafe(32)
    if HOST not in ('127.0.0.1', 'localhost') and not os.environ.get('ABAQUS_VIEWER_TOKEN'):
        raise ValueError('Non-loopback binding requires an explicit ABAQUS_VIEWER_TOKEN')
    if not (STATIC_DIR / 'index.html').is_file():
        raise RuntimeError('Viewer assets missing. Run npm ci and npm run build in viewer/.')
    server = http.server.ThreadingHTTPServer((HOST, PORT), ViewerHandler)
    server.token = token
    server.exports = ExportManager(os.environ.get('ABAQUS_VIEWER_EXPORT_ROOT', Path.home() / '.abaqus-mcp-pro/exports'))
    from abaqus_mcp_pro.viewer_bridge import session_file
    registry = session_file()
    registry.parent.mkdir(parents=True, exist_ok=True)
    actual_port = server.server_address[1]
    registry.write_text(json.dumps({'url': f'http://{HOST}:{actual_port}', 'token': token}), encoding='utf-8')
    registry.chmod(0o600)
    print(f'Open http://{HOST}:{actual_port}/#token={token}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.exports.close()


if __name__ == '__main__':
    main()
