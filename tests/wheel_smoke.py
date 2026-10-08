"""Run with an isolated installed-wheel Python, without adding src to sys.path."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import queue
import subprocess
import sys
import threading
import time
import urllib.request


def check_stdio():
    process = subprocess.Popen([sys.executable, '-m', 'abaqus_mcp_pro.server'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8')
    messages = queue.Queue()
    reader = threading.Thread(target=lambda: [messages.put(line) for line in process.stdout], daemon=True)
    reader.start()
    def send(value):
        process.stdin.write(json.dumps(dict(jsonrpc='2.0', **value)) + '\n')
        process.stdin.flush()
    def receive(identifier):
        result = json.loads(messages.get(timeout=15))
        assert result['id'] == identifier and 'error' not in result, result
        return result['result']
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18',
              'capabilities': {}, 'clientInfo': {'name': 'wheel-smoke', 'version': '1'}}})
        assert receive(1)['serverInfo']['name'] == 'abaqus-mcp-pro'
        send({'method': 'notifications/initialized'})
        send({'id': 2, 'method': 'tools/list', 'params': {}})
        assert len(receive(2)['tools']) == 138
        send({'id': 3, 'method': 'resources/list', 'params': {}})
        assert len(receive(3)['resources']) == 74
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        reader.join(5)
        process.stdout.close()
        process.stderr.close()


async def main():
    with tempfile.TemporaryDirectory() as directory:
        os.environ['ABAQUS_MCP_PLUGIN_DIR'] = directory
        check_stdio()
        from abaqus_mcp_pro import server
        assert Path(server.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), server.__file__
        from abaqus_mcp_pro.viewer import serve_viewer
        tools = await server.mcp.list_tools()
        prompts = await server.mcp.list_prompts()
        resources = await server.mcp.list_resources()
        assert len(tools) == 138, len(tools)
        assert len(prompts) == 13, len(prompts)
        assert len(resources) == 74, len(resources)
        assert all(tool.annotations is not None for tool in tools)
        assert (serve_viewer.STATIC_DIR / 'index.html').is_file()
        assert (serve_viewer.VIEWER_DIR / 'export/run_export.py').is_file()
        from abaqus_mcp_pro import workflow
        assert len(workflow.validate_manifest(Path(workflow.__file__).parent / 'data/verification/suite.json')['cases']) == 6
        assert (Path(directory) / 'abaqus_mcp_pro_runtime/agent.py').is_file()
        session_path = Path(directory) / 'viewer-session.json'
        env = dict(os.environ, ABAQUS_VIEWER_PORT='0', ABAQUS_VIEWER_HOST='127.0.0.1',
                   ABAQUS_VIEWER_SESSION_FILE=str(session_path), ABAQUS_VIEWER_EXPORT_ROOT=str(Path(directory) / 'exports'))
        with (Path(directory) / 'viewer.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'abaqus_mcp_pro.viewer.serve_viewer'], env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while not session_path.exists() and time.monotonic() < deadline:
                    time.sleep(.1)
                session = json.loads(session_path.read_text())
                with urllib.request.urlopen(session['url']) as page:
                    html = page.read().decode('utf-8')
                    assert 'welcome-open-odb' in html and 'welcome-load-sample' not in html
                    assert 'no-store' in page.headers['Cache-Control']
                from abaqus_mcp_pro.viewer_bridge import request
                assert request(session, '/api/health')['viewer_protocol'] == 2
                assert request(session, '/api/tasks') == {'tasks': []}
                from abaqus_mcp_pro.projects import history
                assert history(directory) == []
            finally:
                process.terminate()
                process.wait(timeout=10)
        print(json.dumps({'tools': len(tools), 'prompts': len(prompts), 'resources': len(resources),
                          'viewer_assets': True, 'plugin_runtime': True, 'stdio_roundtrip': True, 'installed_viewer_http': True}))


if __name__ == '__main__':
    asyncio.run(main())
