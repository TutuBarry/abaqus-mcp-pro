"""Exercise a bridge started from the real CAE menu; retain evidence in a new directory."""
import argparse
import json
from pathlib import Path
import time
from abaqus_mcp_pro.client import AbaqusBridgeClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--existing-job',help='Resume verification of an already submitted job in this output directory')
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True,exist_ok=True)
    source = Path(__file__).resolve().parents[1]/'examples/verification/rod.inp'
    (root/'analysis.inp').write_text(source.read_text().replace('{{LOAD}}','1000'),encoding='ascii')
    client = AbaqusBridgeClient(timeout=20)
    record = {'ping':client.ping()}
    name = args.existing_job or 'MCP_RC2_' + str(int(time.time()))
    code = 'import os\nfrom abaqus import mdb\nprevious_directory = os.getcwd()\nos.chdir({!r})\njob = mdb.JobFromInputFile(name={!r},inputFileName="analysis.inp")\njob.submit()\nresult={{"job":{!r},"status":str(job.status),"previous_directory":previous_directory}}'.format(str(root),name,name)
    record['submit'] = client.execute(code) if not args.existing_job else client.execute('result={"job":'+repr(name)+',"previous_directory":previous_directory}')
    deadline = time.monotonic()+120
    while time.monotonic() < deadline:
        response = client.execute('from abaqus import mdb\nresult={"status":str(mdb.jobs['+repr(name)+'].status)}')
        status = response.get('return_value',{}).get('status','')
        record['monitor'] = response
        if status in ('COMPLETED','ABORTED','TERMINATED'):
            break
        time.sleep(1)
    odb = root/(name+'.odb')
    if status != 'COMPLETED' or not odb.is_file():
        raise RuntimeError('GUI job did not complete: '+str(record))
    record['open'] = client.request('odb_open',{'path':str(odb),'read_only':True})
    record['summary'] = client.request('odb_summary',{'handle':record['open']['handle']})
    record['kernel'] = client.execute('result={"answer":6*7}')
    record['close'] = client.request('odb_close',{'handle':record['open']['handle']})
    previous = record['submit'].get('return_value',{}).get('previous_directory')
    if previous:
        client.execute('import os\nos.chdir('+repr(previous)+')\nresult={"restored":True}')
    record['passed'] = record['kernel'].get('return_value',{}).get('answer') == 42
    (root/'report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':record['passed'],'directory':str(root)},ensure_ascii=False))


if __name__ == '__main__':
    main()
