import json
from pathlib import Path
import pytest
from abaqus_mcp_pro.projects import compare, export_report, history
from abaqus_mcp_pro.plugin_install import install_plugin
from test_delivery_regressions import viewer


def run_fixture(root, name='one', units='N-mm-s-tonne', component='U1', status='passed', value=2):
    root = root/name
    root.mkdir()
    (root/'run.json').write_text(json.dumps({'run_id':name,'unit_system':units,'cases':[
        {'id':'case','status':status,'kpis':{'u':value},'parameters':{'LOAD':1000}}]}))
    (root/'manifest.json').write_text(json.dumps({'cases':[{'id':'case','queries':[
        {'query_id':'u','field':'U','component':component}]}]}))
    return root


def test_comparison_keeps_selectors_separate_and_failed_cases_visible(tmp_path):
    one = run_fixture(tmp_path)
    two = run_fixture(tmp_path,'two',value=4)
    three = run_fixture(tmp_path,'three',component='U2',value=30)
    four = run_fixture(tmp_path,'four',status='failed',value=999)
    rows = compare([one,two,three,four])
    assert [r['change_percent'] for r in rows] == [0,100,0,None]
    assert not rows[-1]['comparable']
    assert len(history(tmp_path)) == 4


def test_comparison_rejects_units_mismatch_and_handles_zero(tmp_path):
    one = run_fixture(tmp_path,value=0)
    two = run_fixture(tmp_path,'two',units='N-m-s-kg')
    assert compare([one])[0]['change_percent'] is None
    with pytest.raises(ValueError,match='unit'):
        compare([one,two])


def test_reports_escape_html_and_keep_evidence(tmp_path):
    rows = compare([run_fixture(tmp_path)])
    rows[0]['case'] = '<script>alert(1)</script>'
    rows[0]['project'] = '=1+1'
    out = export_report(rows,tmp_path/'report')
    assert '<script>' not in (out/'comparison.html').read_text(encoding='utf-8')
    assert "'=1+1" in (out/'comparison.csv').read_text(encoding='utf-8-sig')
    assert json.loads((out/'comparison.json').read_text(encoding='utf-8'))[0]['selector']['component'] == 'U1'


def test_plugin_install_preserves_and_disables_recognized_legacy(tmp_path,monkeypatch):
    monkeypatch.setenv('ABAQUS_MCP_PLUGIN_DIR',str(tmp_path))
    legacy = tmp_path/'abaqus_mcp_gui_plugin.py'
    content = 'def start_gui_agent(): pass\n# ABAQUS MCP Pro|Start MCP Bridge'
    legacy.write_text(content)
    install_plugin()
    assert not legacy.exists()
    assert next(tmp_path.glob('*.disabled-*')).read_text() == content
    install_plugin()
    assert len(list(tmp_path.glob('*.disabled-*'))) == 1


def test_task_history_sorted_and_diagnostics_bounded(tmp_path):
    manager = viewer.ExportManager(tmp_path)
    try:
        for i in range(3):
            task = {'task_id':str(i),'created_at':i,'status':'failed','error':'fixture'}
            manager.tasks[str(i)] = task
            manager.save(task)
        (tmp_path/'2/export.log').write_text('x'*20000)
        assert [t['task_id'] for t in manager.history(2)] == ['2','1']
        assert len(manager.diagnostics('2')['log_tail']) == 16384
        with pytest.raises(KeyError):
            manager.diagnostics('../outside')
    finally:
        manager.close()
