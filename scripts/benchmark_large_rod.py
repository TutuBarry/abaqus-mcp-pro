"""Real scalable truss solve/export; measures line meshes, not solid-contact scaling."""
import argparse
import json
from pathlib import Path
import time
import uuid
from abaqus_mcp_pro.commands import find_abaqus_command
from abaqus_mcp_pro.viewer_bridge import ensure_viewer, request
from abaqus_mcp_pro.workflow import run_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--elements',type=int,nargs='+',default=[10000,100000,1000000])
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True,exist_ok=True)
    records = []
    for count in args.elements:
        if not 1 <= count <= 1000000:
            raise ValueError('Expected 1..1000000 elements')
        directory = root/str(count)
        directory.mkdir(exist_ok=True)
        with (directory/'analysis.inp').open('w') as stream:
            stream.write('*HEADING\nReal axial truss scaling benchmark: N-mm\n*NODE\n')
            for i in range(count+1):
                stream.write('%d, %.12g, 0, 0\n' % (i+1,100*i/count))
            stream.write('*ELEMENT, TYPE=T3D2, ELSET=BODY\n')
            for i in range(count):
                stream.write('%d, %d, %d\n' % (i+1,i+1,i+2))
            stream.write('''*NSET, NSET=ALL, GENERATE
1, {last}, 1
*NSET, NSET=TIP
{last}
*NSET, NSET=FIXED
1
*SOLID SECTION, ELSET=BODY, MATERIAL=ELASTIC
10
*MATERIAL, NAME=ELASTIC
*ELASTIC
210000, 0.3
*BOUNDARY
ALL, 2, 3
FIXED, 1, 1
*STEP, NAME=Load
*STATIC
*CLOAD
TIP, 1, 1000
*OUTPUT, FIELD
*NODE OUTPUT
U, RF
*ELEMENT OUTPUT
S
*END STEP
'''.format(last=count+1))
        record = {'elements':count,'nodes':count+1,'directory':str(directory),'status':'running'}
        records.append(record)
        try:
            command = find_abaqus_command()
            start = time.monotonic()
            code = run_process([command,'job=analysis','input=analysis.inp','interactive','cpus=2','ask_delete=OFF'],
                               directory,directory/'solver.log',300)
            record['solver_seconds'] = time.monotonic()-start
            sta = directory/'analysis.sta'
            if code or not sta.is_file() or 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in sta.read_text():
                raise RuntimeError('Solver incomplete')
            (directory/'inspect.py').write_text('''from odbAccess import openOdb
import json
odb=openOdb('analysis.odb',readOnly=True)
try:
    frame=list(odb.steps.values())[-1].frames[-1]
    inst=list(odb.rootAssembly.instances.values())[0]
    values=frame.fieldOutputs['U'].getSubset(region=inst.nodeSets['TIP']).values
    u=float(values[0].data[0])
    reaction=sum(float(v.data[0]) for v in frame.fieldOutputs['RF'].getSubset(region=inst.nodeSets['FIXED']).values)
    passed=abs(u-1000.*100/(210000*10)) < 1e-5 and abs(reaction+1000) < .1
    with open('validation.json','w') as stream: json.dump(dict(u_mm=u,reaction_N=reaction,passed=passed),stream)
finally:
    odb.close()
''',encoding='ascii')
            code = run_process([command,'python','inspect.py'],directory,directory/'inspect.log',120)
            if code: raise RuntimeError('Inspection failed')
            record['validation'] = json.loads((directory/'validation.json').read_text())
            if not record['validation']['passed']: raise RuntimeError('Numeric reference failed')
            session = ensure_viewer()
            start = time.monotonic()
            task = request(session,'/api/export',{'odb_path':str(directory/'analysis.odb'),'unit_system':'N-mm-s-tonne',
                           'fields':['U'],'request_id':uuid.uuid4().hex})
            deadline = start+600
            while task['status'] in ('queued','running') and time.monotonic()<deadline:
                time.sleep(.5)
                task = request(session,'/api/tasks/'+task['task_id'])
            record.update(export=task,export_seconds=time.monotonic()-start,
                          status='passed' if task['status']=='completed' else 'failed_export')
        except Exception as exc:
            record.update(status='failed',error=str(exc))
        (root/'report.json').write_text(json.dumps({'scope':'Real connected T3D2 rod; U-only export, not solid-contact or GPU scaling','cases':records},indent=2),encoding='utf-8')
        print(count,record['status'],flush=True)
    if any(r['status'] != 'passed' for r in records): raise SystemExit(2)


if __name__ == '__main__':
    main()
