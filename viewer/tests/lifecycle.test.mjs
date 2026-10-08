import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Viewer3D} from '../src/viewer3d.js';
import {filterSurfaceIndices} from '../src/vtuparser.js';

test('late frame response cannot restore geometry after clearing result', async t => {
  let finish;
  const response = new Promise(resolve => {finish = resolve;});
  t.mock.method(globalThis, 'fetch', () => response);
  const viewer = new Viewer3D('unused');
  const loading = viewer.buildSceneFromVTU({format_version:'3.0', frames:[{vtu_file:'frame.vtu'}]});
  viewer.clearResult();
  finish({ok:true, text:async () => 'must never parse this stale frame'});
  await loading;
  assert.equal(viewer._lastVtuResult, null);
  assert.equal(viewer.meshGroup.children.length, 0);
});

test('body filtering hides only the selected body', () => {
  const indices = [0,1,2,3,4,5];
  assert.deepEqual(filterSurfaceIndices(indices, [0,0,0,1,1,1], [1], [], false), [0,1,2]);
  assert.deepEqual(filterSurfaceIndices(indices, [0,0,0,1,1,1], [0,1], [], false), []);
});

test('contact-only surface never bridges nodes without output', () => {
  const indices = [0,1,2,1,2,3];
  assert.deepEqual(filterSurfaceIndices(indices, [], [], [10,0,5,NaN], true), [0,1,2]);
});

test('statistics count cells, not triangulated faces', () => {
  const viewer = new Viewer3D('unused');
  viewer._lastVtuResult = {positions: Array(24).fill(0), cells: [Array(8).fill(0)], indices:Array(36).fill(0)};
  assert.deepEqual(viewer.getVtuStats(), {nodes:8, elements:1});
});
