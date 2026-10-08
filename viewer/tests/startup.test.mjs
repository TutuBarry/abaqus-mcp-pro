import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ODBExportClient, resultSelection} from '../src/odbexport.js';

const id = '37c9c625eece42ae8c2039bdf5cac2a7';
const result = {task_id: id, status: 'completed', output_url: `/exports/${id}/model.json`,
  params: {odb_path: 'E:\\runs\\contact\\analysis.odb'}};

test('static result defaults to final frame and Mises; explicit selectors win', () => {
  const s11 = {name: 'S_S11'}, mises = {name: 'S_mises'};
  const data = {frames: Array(11).fill({}), fields: [s11, mises]};
  assert.deepEqual(resultSelection(data, '?frame=last&field=S_mises'), {frameIdx: 10, field: mises});
  assert.deepEqual(resultSelection(data, ''), {frameIdx: 0, field: mises});
  data.steps = [{procedure: 'STATIC'}];
  assert.deepEqual(resultSelection(data, ''), {frameIdx: 10, field: mises});
  assert.deepEqual(resultSelection(data, '?frame=0&field=S_S11'), {frameIdx: 0, field: s11});
  assert.throws(() => resultSelection(data, '?frame=11'), /帧不存在/);
  assert.throws(() => resultSelection(data, '?field=CPRESS'), /场变量不存在/);
});

function setup(t, search = '') {
  const elements = new Map();
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('Unexpected fetch'); });
  for (const [name, value] of Object.entries({
    location: {search, hash: '', pathname: '/', href: 'http://localhost:8087/' + search},
    history: {replaceState(_state, _title, url) { this.url = url; }},
    document: {getElementById(key) {
      if (!elements.has(key)) elements.set(key, {value: '', textContent: '', classList: {add() {}, remove() {}}});
      return elements.get(key);
    }},
  })) {
    const previous = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, {value, configurable: true});
    t.after(() => previous ? Object.defineProperty(globalThis, name, previous) : delete globalThis[name]);
  }
  const loaded = [];
  const ui = {_updateStatus(value) { this.status = value; }, _setFileBadge(value) { this.badge = value; }};
  const client = new ODBExportClient({}, {}, ui);
  client._loadExportedJson = async path => { loaded.push(path); };
  return {client, loaded, elements, ui};
}

test('ordinary startup does not request or load any model', async t => {
  const {client, loaded} = setup(t);
  await client.loadStartupResult();
  assert.deepEqual(loaded, []);
  assert.equal(fetch.mock.callCount(), 0);
});

test('result link loads exactly the requested task and retains its source', async t => {
  const {client, loaded, ui} = setup(t, '?task=' + id);
  fetch.mock.mockImplementation(async path => {
    assert.equal(path, '/api/tasks/' + id);
    return {ok: true, json: async () => result};
  });
  await client.loadStartupResult();
  assert.deepEqual(loaded, [result.output_url]);
  assert.equal(ui.badge, result.params.odb_path);
  assert.equal(history.url, '/?task=' + id);
});

for (const status of ['failed', 'running', 'cancelled']) {
  test(status + ' task displays error without loading another result', async t => {
    const {client, loaded, ui} = setup(t, '?task=' + id);
    fetch.mock.mockImplementation(async () => ({ok: true, json: async () => ({...result, status})}));
    await client.loadStartupResult();
    assert.deepEqual(loaded, []);
    assert.match(ui.status, /结果加载失败/);
  });
}

test('missing result reports failure without sample fallback', async t => {
  const {client, loaded, ui} = setup(t, '?task=' + id);
  fetch.mock.mockImplementation(async () => ({ok: false}));
  await client.loadStartupResult();
  assert.deepEqual(loaded, []);
  assert.match(ui.status, /结果加载失败/);
});

test('successful export updates URL so refresh selects that same result', async t => {
  const {client, loaded} = setup(t);
  await client.loadTaskResult(result);
  assert.deepEqual(loaded, [result.output_url]);
  assert.equal(history.url, '/?task=' + id);
  assert.equal(client.state.exportTaskId, id);
});
