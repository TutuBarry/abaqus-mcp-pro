"""API shapes and launcher behavior observed in real Abaqus 2026 on Windows."""
import sys
from types import SimpleNamespace as NS

from abaqus_mcp_pro import agent, commands, nogui


def test_explicit_command_has_priority(monkeypatch):
    monkeypatch.setenv('ABAQUS_COMMAND', 'custom-launcher')
    assert commands.find_abaqus_command() == 'custom-launcher'


def test_install_found_when_running_process_has_stale_path(monkeypatch):
    monkeypatch.delenv('ABAQUS_COMMAND', raising=False)
    monkeypatch.setattr(commands.shutil, 'which', lambda name: None)
    # Avoid changing os.name globally: pathlib and pytest rely on its real value.
    if commands.os.name != 'nt':
        return
    monkeypatch.setattr(commands.Path, 'is_file', lambda path: str(path).replace('\\', '/') == 'D:/Program Files/SIMULIA/Commands/abaqus.bat')
    assert commands.find_abaqus_command().replace('\\', '/') == 'D:/Program Files/SIMULIA/Commands/abaqus.bat'


def test_field_value_array_does_not_require_slice_or_invalid_invariant(monkeypatch):
    class Values:
        def __len__(self):
            return 6000
        def __getitem__(self, key):
            assert isinstance(key, int), 'FieldValueArray rejects slices'
            return NS(data=(1., 2., 3.), instance=NS(name='PART-1-1'), nodeLabel=key + 1)
    field = NS(values=Values(), validInvariants=())
    frame = NS(fieldOutputs={'U': field}, frameValue=1.)
    odb = NS(steps={'Load': NS(frames=[frame])})
    monkeypatch.setitem(agent._OPEN_ODBS, 'real-shape', odb)
    result = agent._extract_field({'handle': 'real-shape', 'field_name': 'U'})
    assert result['total_values'] == 6000 and result['truncated']
    assert len(result['values']) == 5000
    assert result['values'][0]['data'] == [1, 2, 3]
    assert 'mises' not in result['values'][0]


def test_model_snapshot_reports_unavailable_repository(monkeypatch):
    model = NS(**{key: {} for key in ('parts', 'materials', 'sections', 'steps', 'loads', 'boundaryConditions', 'interactions')},
               rootAssembly=NS(instances={}, sets={}, surfaces={}))
    monkeypatch.setitem(sys.modules, 'abaqus', NS(mdb=NS(models={'New': model}, jobs={})))
    result = agent._mdb_info()['models']['New']
    assert result['constraints'] == []
    assert result['unavailable_repositories'] == ['constraints']


def test_launcher_error_with_zero_exit_code_is_failure(monkeypatch, tmp_path):
    from abaqus_mcp_pro import workflow
    def runner(command, cwd, log, timeout):
        log.write_text('NameError: test\nAbaqus Error: cae exited with an error.\n')
        return 0
    monkeypatch.setattr(workflow, 'run_process', runner)
    result = nogui._run_abaqus_subprocess(['cae', 'noGUI=test.py'], cwd=str(tmp_path))
    assert result['return_code'] == 0 and not result['ok']
    assert 'cae exited' in result['error']
