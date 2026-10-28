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
    parser.add_argument('--levels', default='1,1.5,2,2.5,3')
    parser.add_argument('--families', default='flat,curved')
    parser.add_argument('--skip-extensions', action='store_true')
    parser.add_argument('--cpus', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    levels_to_run = [level.strip() for level in args.levels.split(',') if level.strip()]
    families_to_run = [family.strip() for family in args.families.split(',') if family.strip()]
    if len(levels_to_run) < 2:
        parser.error('--levels must contain at least two refinement levels')
    if not families_to_run or any(family not in ('flat', 'curved') for family in families_to_run):
        parser.error('--families must contain flat and/or curved')
    if args.cpus < 1:
        parser.error('--cpus must be at least 1')
    if args.timeout <= 0:
        parser.error('--timeout must be greater than zero')
    repo = Path(__file__).resolve().parents[1]
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    command = find_abaqus_command()
    records = []
    extension_modes = [] if args.skip_extensions else [
        ('friction', ['--friction', '0.2', '--slide', '0.5'], ['--expect-friction']),
        ('plastic', ['--plastic'], ['--expect-plastic']),
    ]
    for mode, options, checks in extension_modes:
        directory = root / mode
        directory.mkdir(exist_ok=True)
        subprocess.run([sys.executable, str(repo/'examples/verification/generate_contact.py'),
                        '--output', str(directory), '--curved', *options], check=True)
        with (directory/'solver.log').open('w') as log:
            subprocess.run([command, 'job=analysis', 'input=analysis.inp', 'interactive',
                            'cpus=' + str(args.cpus), 'ask_delete=OFF'],
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
    for mode in families_to_run:
        levels = []
        for level in levels_to_run:
            directory = Path(args.baseline).resolve()/mode/level
            if not (directory/'analysis.odb').is_file():
                directory = root/'convergence'/mode/level
                directory.mkdir(parents=True, exist_ok=True)
                generator = [sys.executable, str(repo/'examples/verification/generate_contact.py'),
                             '--output', str(directory), '--refinement', level]
                if mode == 'curved':
                    generator.append('--curved')
                subprocess.run(generator, check=True, timeout=120)
                with (directory/'solver.log').open('w') as log:
                    subprocess.run([command, 'job=analysis', 'input=analysis.inp', 'interactive',
                                    'cpus=' + str(args.cpus), 'ask_delete=OFF'],
                                   cwd=directory, stdout=log, stderr=log, check=True,
                                   timeout=args.timeout)
                sta = directory/'analysis.sta'
                if not sta.exists() or 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in sta.read_text():
                    raise RuntimeError(f'Solver incomplete: {mode} refinement {level}')
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
        target_metrics = ['peak_pressure_MPa','peak_mises_MPa'] if mode == 'flat' else ['area_mm2']
        within_five = {k:v < .05 for k,v in changes.items()}
        convergence.append({
            'family':mode,
            'levels':levels,
            'last_two_relative_changes':changes,
            'within_5_percent':within_five,
            'target_metrics':target_metrics,
            'target_passed':all(within_five[k] for k in target_metrics),
        })
    report = {'extensions':records, 'extensions_skipped':args.skip_extensions,
              'convergence':convergence,
              'extension_checks_passed':None if args.skip_extensions else all(r['passed'] for r in records),
              'note':'Illustrative materials; area is undeformed projected nodal estimate. Each convergence metric is reported independently.'}
    (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if (
        (not args.skip_extensions and not report['extension_checks_passed'])
        or not all(item['target_passed'] for item in report['convergence'])
    ):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
