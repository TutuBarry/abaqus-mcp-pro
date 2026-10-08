"""Local run history and comparable KPI reports; no solver is launched by this command."""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path


def history(root):
    records = []
    for file in sorted(Path(root).resolve().glob('*/run.json'), reverse=True):
        try:
            run = json.loads(file.read_text(encoding='utf-8'))
            records.append({'run_id': run['run_id'], 'project': run.get('project', ''),
                            'created_at': run.get('created_at', ''), 'status': run.get('status', 'in_progress'),
                            'cases': len(run['cases']), 'path': str(file)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            records.append({'path': str(file), 'status': 'unreadable', 'error': str(exc)})
    return records


def compare(paths):
    """Compare scalar KPIs only within matching units and selectors.

    Prepared/failed cases remain visible, but never become numeric baselines.
    First accepted value for each KPI + selector is the comparison baseline.
    """
    rows, baseline = [], {}
    units = None
    for path in paths:
        path = Path(path).resolve()
        if path.is_dir():
            path /= 'run.json'
        run = json.loads(path.read_text(encoding='utf-8'))
        current_units = run.get('unit_system')
        if not current_units or (units is not None and units != current_units):
            raise ValueError('Comparison requires the same declared unit system')
        units = current_units
        manifest = path.with_name('manifest.json')
        selectors = {}
        if manifest.is_file():
            for case in json.loads(manifest.read_text(encoding='utf-8'))['cases']:
                selectors[case['id']] = {q['query_id']: {k:v for k,v in q.items() if k != 'query_id'} for q in case['queries']}
        for case in run['cases']:
            for name, value in (case.get('kpis') or {'':None}).items():
                selector = selectors.get(case['id'], {}).get(name)
                # Missing selectors cannot be silently equated across jobs.
                comparable = case['status'] == 'passed' and selector is not None and type(value) in (int,float) and math.isfinite(value)
                key = (name, json.dumps(selector, sort_keys=True))
                reference = baseline.setdefault(key, value) if comparable else None
                delta = (value-reference)/abs(reference)*100 if reference not in (None,0) else None
                rows.append({'run_id':run['run_id'], 'project':run.get('project',''), 'case':case['id'],
                             'status':case['status'], 'units':units, 'parameters':case.get('parameters',{}),
                             'kpi':name, 'value':value, 'baseline':reference, 'change_percent':delta,
                             'comparable':comparable, 'selector':selector, 'error':case.get('error',''),
                             'evidence':str(path.parent/case['id']), 'input_sha256':case.get('input_sha256',''),
                             'odb_sha256':case.get('odb_sha256','')})
    return rows


def export_report(rows, output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root/'comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    columns = ['run_id','project','case','status','units','parameters','kpi','value','baseline','change_percent','comparable','selector','error','evidence','input_sha256','odb_sha256']
    def display(value):
        return json.dumps(value,ensure_ascii=False,sort_keys=True) if isinstance(value,(dict,list)) else '' if value is None else str(value)
    with (root/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for row in rows:
            values = [display(row[k]) for k in columns]
            # Keep arbitrary project/case text inert in spreadsheet applications.
            writer.writerow(["'"+v if v.startswith(('=','+','@','\t','\r')) or (v.startswith('-') and type(row[k]) not in (int,float)) else v for k,v in zip(columns,values)])
    visible = ['run_id','case','status','parameters','kpi','value','change_percent','error']
    table = '<tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in visible)+'</tr>'
    for row in rows:
        table += '<tr>'+''.join('<td>'+html.escape(display(row[k]))+'</td>' for k in visible)+'</tr>'
    document = '<!doctype html><html lang="zh"><meta charset="utf-8"><title>仿真对比报告</title><style>body{font:15px system-ui;margin:32px;color:#17202a}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;text-align:left}th{background:#eef2f5}</style><h1>仿真对比报告</h1><p>仅相同单位与 KPI 选择条件的通过项参与比较；首个通过值作为基准。零基准不计算百分比。详细选择条件、输入及 ODB 哈希见配套 JSON/CSV。</p><p>单位：'+html.escape(rows[0]['units'] if rows else '')+'</p><table>'+table+'</table></html>'
    (root/'comparison.html').write_text(document,encoding='utf-8')
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action',required=True)
    listing = sub.add_parser('history')
    listing.add_argument('root')
    report = sub.add_parser('compare')
    report.add_argument('runs',nargs='+')
    report.add_argument('--output',required=True)
    args = parser.parse_args()
    if args.action == 'history':
        result = history(args.root)
    else:
        rows = compare(args.runs)
        result = {'output':str(export_report(rows,args.output)), 'rows':len(rows)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
