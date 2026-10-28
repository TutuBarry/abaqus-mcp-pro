"""Licensed 124k-node contact benchmark with bounded runtime and sampled export."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
from abaqus_mcp_pro.commands import find_abaqus_command
from abaqus_mcp_pro.viewer_bridge import ensure_viewer, request
from abaqus_mcp_pro.workflow import run_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--timeout',type=float,default=600,
                        help='Solver timeout in seconds')
    parser.add_argument('--cpus',type=int,default=2,
                        help='Abaqus solver CPU count')
    parser.add_argument('--export-timeout',type=float,default=600,
                        help='Viewer export timeout in seconds')
    args = parser.parse_args()
    if args.timeout <= 0 or args.export_timeout <= 0:
        parser.error('timeouts must be greater than zero')
    if args.cpus < 1:
        parser.error('cpus must be at least 1')
    root = Path(args.output).resolve()
    root.mkdir(parents=True,exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    command = find_abaqus_command()
    generator = [sys.executable,str(repo/'examples/verification/generate_contact.py'),
                 '--output',str(root),'--curved','--refinement','4']
    subprocess.run(generator,check=True)
    start = time.monotonic()
    try:
        code = run_process([command,'job=analysis','input=analysis.inp','interactive',
                            'cpus='+str(args.cpus),'timeout='+str(int(args.timeout)),
                            'ask_delete=OFF'],
                           root,root/'solver.log',args.timeout)
    except subprocess.TimeoutExpired:
        (root/'report.json').write_text(json.dumps({
            'status':'timed_out',
            'timeout_seconds':args.timeout,
            'cpus':args.cpus,
            'generator':generator,
            'completed':False,
            'exported':False,
            'elapsed_seconds':time.monotonic()-start,
        },indent=2),encoding='utf-8')
        raise SystemExit(2)
    if code or not (root/'analysis.sta').is_file() or 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in (root/'analysis.sta').read_text():
        raise RuntimeError('Large model solver did not complete')
    record = {'solver_seconds':time.monotonic()-start,'timeout_seconds':args.timeout,
              'cpus':args.cpus,'generator':generator}
    with (root/'inspect.log').open('w') as log:
        subprocess.run([command,'python',str(repo/'scripts/inspect_contact_odb.py'),str(root/'analysis.odb'),
                        str(root/'validation.json')],stdout=log,stderr=log,check=True)
    record['validation'] = json.loads((root/'validation.json').read_text())
    session = ensure_viewer()
    start = time.monotonic()
    task = request(session,'/api/export',{'odb_path':str(root/'analysis.odb'),'unit_system':'N-mm-s-tonne',
                   'fields':['S','U','CPRESS','COPEN'],'frame_step':5,'request_id':uuid.uuid4().hex})
    deadline = start+args.export_timeout
    while task['status'] in ('queued','running') and time.monotonic()<deadline:
        time.sleep(.5)
        task = request(session,'/api/tasks/'+task['task_id'])
    record.update(export=task,export_seconds=time.monotonic()-start)
    (root/'report.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({'nodes':record['validation']['nodes'],'solver_seconds':record['solver_seconds'],
                      'export_status':task['status'],'export_seconds':record['export_seconds'],'task_id':task['task_id']}))
    record['export_timeout_seconds'] = args.export_timeout
    (root/'report.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    if task['status'] != 'completed' or not record['validation']['passed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
