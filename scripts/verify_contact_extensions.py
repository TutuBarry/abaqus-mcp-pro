"""Run real friction/plastic examples and refresh pressure/area convergence evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from abaqus_mcp_pro.commands import find_abaqus_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--baseline', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    command = find_abaqus_command()
    records = []
    for mode, options, checks in [
        ('friction', ['--friction', '0.2', '--slide', '0.5'], ['--expect-friction']),
        ('plastic', ['--plastic'], ['--expect-plastic']),
    ]:
        directory = root / mode
        directory.mkdir(exist_ok=True)
        subprocess.run([sys.executable, str(repo/'examples/verification/generate_contact.py'),
                        '--output', str(directory), '--curved', *options], check=True)
        with (directory/'solver.log').open('w') as log:
            subprocess.run([command, 'job=analysis', 'input=analysis.inp', 'interactive', 'cpus=2', 'ask_delete=OFF'],
                           cwd=directory, stdout=log, stderr=log, check=True, timeout=600)
        sta = directory/'analysis.sta'
        if not sta.exists() or 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in sta.read_text():
            raise RuntimeError('Solver incomplete: ' + mode)
        with (directory/'inspect.log').open('w') as log:
            subprocess.run([command, 'python', str(repo/'scripts/inspect_contact_odb.py'),
                            str(directory/'analysis.odb'), str(directory/'validation.json'), *checks],
                           cwd=directory, stdout=log, stderr=log, check=True, timeout=120)
        result = json.loads((directory/'validation.json').read_text())
        records.append({'mode':mode, 'passed':result['passed'], 'checks':result['checks'],
                        'force_N':result['force_N'], 'energies':result['energies'], 'peeq_max':result['peeq_max']})
        print(mode, records[-1], flush=True)
    convergence = []
    for mode in ('flat', 'curved'):
        levels = []
        for level in ('1', '1.5', '2'):
            directory = Path(args.baseline).resolve()/mode/level
            target = root/(mode+'-'+level+'.json')
            with (root/(mode+'-'+level+'.log')).open('w') as log:
                subprocess.run([command, 'python', str(repo/'scripts/inspect_contact_odb.py'),
                                str(directory/'analysis.odb'), str(target)], stdout=log, stderr=log, check=True)
            result = json.loads(target.read_text())
            levels.append({'refinement':level, 'passed':result['passed'], 'force_N':result['force_N'],
                           'area_mm2':result['contact_area_projected_nodal_estimate_mm2'],
                           'peak_pressure_MPa':max(v['max'] for k,v in result['contact'].items() if k.startswith('CPRESS')),
                           'peak_mises_MPa':result['mises_MPa'][1],
                           'pressure_force_relative_difference':result['pressure_force_relative_difference']})
        changes = {k:abs(levels[-1][k]-levels[-2][k])/max(abs(levels[-1][k]),1e-12)
                   for k in ('force_N','area_mm2','peak_pressure_MPa','peak_mises_MPa')}
        convergence.append({'family':mode, 'levels':levels, 'last_two_relative_changes':changes,
                            'within_5_percent':{k:v < .05 for k,v in changes.items()}})
    report = {'extensions':records, 'convergence':convergence,
              'extension_checks_passed':all(r['passed'] for r in records),
              'note':'Illustrative materials; area is undeformed projected nodal estimate. Each convergence metric is reported independently.'}
    (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['extension_checks_passed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
