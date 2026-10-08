"""Real three-level contact refinement; geometric corner peaks are not convergence KPIs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from abaqus_mcp_pro.commands import find_abaqus_command

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args()
root = Path(args.output).resolve()
repo = Path(__file__).resolve().parents[1]
command = find_abaqus_command()
records = []
for curved in (False, True):
    family = []
    for refinement in (1, 1.5, 2):
        directory = root / ('curved' if curved else 'flat') / str(refinement)
        directory.mkdir(parents=True, exist_ok=True)
        generate = [sys.executable, str(repo / 'examples/verification/generate_contact.py'),
                    '--output', str(directory), '--refinement', str(refinement)]
        if curved: generate.append('--curved')
        inp = directory / 'analysis.inp'
        previous = inp.read_bytes() if inp.exists() else None
        subprocess.run(generate, check=True)
        started = time.monotonic()
        existing = directory / 'analysis.sta'
        reuse = previous == inp.read_bytes() and existing.exists() and 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in existing.read_text()
        if not reuse:
          with (directory / 'solver.log').open('w') as log:
            subprocess.run([command, 'job=analysis', 'input=analysis.inp', 'interactive', 'cpus=2', 'ask_delete=OFF'],
                           cwd=directory, stdout=log, stderr=log, check=True, timeout=600)
        if 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in (directory / 'analysis.sta').read_text():
            raise RuntimeError('Solver did not complete: ' + str(directory))
        with (directory / 'inspect.log').open('w') as log:
            subprocess.run([command, 'python', str(repo / 'scripts/inspect_contact_odb.py'),
                            str(directory / 'analysis.odb'), str(directory / 'validation.json')],
                           cwd=directory, stdout=log, stderr=log, check=True)
        record = json.loads((directory / 'validation.json').read_text())
        record.update(refinement=refinement, directory=str(directory), reused_solver=reuse, solver_and_inspection_seconds=time.monotonic()-started)
        family.append(record)
        print(('curved' if curved else 'flat'), refinement, record['passed'], record['force_N'], flush=True)
        (root / 'progress.json').write_text(json.dumps(records + family, indent=2))
    change = abs(family[-1]['force_N']-family[-2]['force_N'])/abs(family[-1]['force_N'])
    records.append({'family': 'curved' if curved else 'flat', 'cases': family,
                    'reaction_relative_change_last_two': change, 'reaction_converged_5_percent': change < .05})
(root / 'report.json').write_text(json.dumps({'families': records,
    'passed': all(f['reaction_converged_5_percent'] and all(c['passed'] for c in f['cases']) for f in records)}, indent=2))
