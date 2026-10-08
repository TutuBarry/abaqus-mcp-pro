"""Reproducible static/contact runs and numeric acceptance from a JSON manifest.

Default is preparation only. --run invokes the licensed local Abaqus installation.
No solver, extraction error, or missing data can produce a PASS.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from . import __version__
from .contracts import check_contracts
from .commands import find_abaqus_command


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def run_process(command, cwd, log_file, timeout):
    with Path(log_file).open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=os.name != 'nt')
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
            else:
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)
            raise


def validate_manifest(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or not manifest.get('unit_system'):
        raise ValueError('schema_version=1 and unit_system are required')
    cases = manifest.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('At least one case is required')
    ids = set()
    for case in cases:
        name = case.get('id', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name) or name in ids:
            raise ValueError('Case IDs must be unique safe names')
        ids.add(name)
        source = (path.parent / case['input_file']).resolve(strict=True)
        if source.suffix.lower() != '.inp' or not source.is_file():
            raise ValueError('Each case needs a real .inp file')
        if not case.get('queries') or not case.get('contracts'):
            raise ValueError('Each case needs KPI queries and acceptance contracts')
        query_ids = [query['query_id'] for query in case['queries']]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError('Duplicate KPI IDs')
        if any(c['kpi_name'] not in query_ids for c in case['contracts']):
            raise ValueError('Contract references an unknown KPI')
        for value in case.get('parameters', {}).values():
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Input substitutions must be finite numeric data')
        source_text = source.read_text(encoding='utf-8')
        for key in re.findall(r'\{\{([^{}]+)\}\}', source_text):
            if key not in case.get('parameters', {}):
                raise ValueError('Unresolved input parameter: ' + key)
    return manifest


def run_manifest(manifest_path, output_root, execute=False, command=None, timeout=600, viewer=False):
    manifest_path = Path(manifest_path).resolve()
    manifest = validate_manifest(manifest_path)
    command = command or find_abaqus_command()
    available = shutil.which(command) is not None or Path(command).is_file()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    root = Path(output_root).resolve() / run_id
    root.mkdir(parents=True)
    shutil.copy2(manifest_path, root / 'source_manifest.json')
    replay = copy.deepcopy(manifest)
    for case in replay['cases']:
        case['input_file'] = case['id'] + '/analysis.inp'
        case['parameters'] = {}
    record = {'run_id': run_id, 'created_at': datetime.now(timezone.utc).isoformat(),
              'manifest_sha256': digest(manifest_path), 'version': __version__,
              'unit_system': manifest['unit_system'], 'python': sys.version,
              'solver_command': command, 'execution_requested': execute, 'cases': []}
    record['project'] = manifest.get('project', manifest_path.stem)
    for case in manifest['cases']:
        directory = root / case['id']
        directory.mkdir()
        source = (manifest_path.parent / case['input_file']).resolve()
        text = source.read_text(encoding='utf-8')
        for name, value in case.get('parameters', {}).items():
            text = text.replace('{{' + name + '}}', repr(value))
        if '{{' in text:
            raise ValueError('Unresolved input parameter in ' + case['id'])
        inp = directory / 'analysis.inp'
        inp.write_text(text, encoding='utf-8')
        state = {'id': case['id'], 'status': 'prepared', 'input_sha256': digest(inp),
                 'source': str(source), 'source_sha256': digest(source), 'reference': case.get('reference', ''),
                 'parameters': case.get('parameters', {}), 'kpis': {}, 'contracts': None}
        record['cases'].append(state)
        if execute and not available:
            state.update(status='solver_unavailable', error='Install Abaqus and set ABAQUS_COMMAND')
        elif execute:
            try:
                state['status'] = 'running'
                write_json(root / 'run.json', record)
                result = run_process([command, 'job=analysis', 'input=analysis.inp', 'cpus=1', 'interactive'],
                                     directory, directory / 'solver.log', timeout)
                sta = directory / 'analysis.sta'
                successful = sta.is_file() and 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in sta.read_text(errors='replace').upper()
                # Modal/other procedures may report completion in the launcher log.
                log = directory / 'analysis.log'
                successful = successful or (log.is_file() and 'ABAQUS JOB ANALYSIS COMPLETED' in log.read_text(errors='replace').upper())
                if result != 0 or not successful or not (directory / 'analysis.odb').is_file():
                    raise RuntimeError('Solver did not produce a confirmed completed ODB')
                config = {'odb_path': str(directory / 'analysis.odb'), 'queries': case['queries'],
                          'result_path': str(directory / 'kpis.json')}
                write_json(directory / 'extract.json', config)
                result = run_process([command, 'python', str(Path(__file__).with_name('workflow_extract.py')),
                                      str(directory / 'extract.json')], directory, directory / 'extract.log', timeout)
                if result != 0:
                    raise RuntimeError('KPI extraction failed; inspect extract.log')
                extracted = json.loads((directory / 'kpis.json').read_text(encoding='utf-8'))
                if extracted['error_count']:
                    raise RuntimeError('KPI extraction contains errors; inspect kpis.json')
                state['kpis'] = {item['query_id']: item['value'] for item in extracted['results']}
                checks = check_contracts(case['contracts'], state['kpis'])
                state['contracts'] = checks.to_dict()
                state['status'] = 'passed' if checks.failed_count == 0 else 'failed_contracts'
                state['odb_sha256'] = digest(directory / 'analysis.odb')
                if viewer:
                    from .viewer_bridge import publish_result
                    try:
                        state['viewer'] = publish_result(str(directory / 'analysis.odb'), manifest['unit_system'])
                    except Exception as exc:
                        state['viewer'] = {'status': 'failed', 'error': str(exc)}
            except Exception as exc:
                state.update(status='failed', error=str(exc))
        write_json(root / 'run.json', record)
    record['status'] = 'passed' if all(c['status'] == 'passed' for c in record['cases']) else 'not_verified'
    write_json(root / 'manifest.json', replay)
    record['replay_manifest_sha256'] = digest(root / 'manifest.json')
    write_json(root / 'run.json', record)
    lines = ['# Simulation acceptance report', '', 'Run: ' + run_id,
             '', '**Status: ' + record['status'] + '**', '',
             'Declared units: ' + record['unit_system'], '',
             '| Case | Status | Evidence |', '|---|---|---|']
    for case in record['cases']:
        lines.append('| ' + case['id'] + ' | ' + case['status'] + ' | ' + case.get('error', 'See run.json and case outputs') + ' |')
    lines += ['', 'A prepared run is not a solver validation. See input/manifest/ODB hashes and KPI selectors in run.json and kpis.json.']
    (root / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return root, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', nargs='?', help='Manifest path; defaults to the bundled static/contact suite')
    parser.add_argument('--output', default='runs')
    parser.add_argument('--run', action='store_true', help='Execute Abaqus, then extract and validate KPIs')
    parser.add_argument('--command', default=None)
    parser.add_argument('--viewer', action='store_true', help='Export each completed ODB and return its local result URL')
    args = parser.parse_args()
    if args.manifest is None:
        bundled = Path(__file__).parent / 'data/verification/suite.json'
        args.manifest = str(bundled if bundled.is_file() else Path(__file__).resolve().parents[2] / 'examples/verification/suite.json')
    root, record = run_manifest(args.manifest, args.output, args.run, args.command, viewer=args.viewer)
    print(json.dumps({'directory': str(root), 'status': record['status'],
                     'viewers': [c.get('viewer') for c in record['cases'] if c.get('viewer')]}, ensure_ascii=False))
    if args.run and record['status'] != 'passed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
