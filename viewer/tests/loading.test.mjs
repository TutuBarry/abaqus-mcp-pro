import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ProgressLoader} from '../src/loader.js';
import {Viewer3D} from '../src/viewer3d.js';

function loader(t) {
  t.mock.timers.enable({apis: ['setTimeout']});
  const classes = new Set();
  const progress = Object.create(ProgressLoader.prototype);
  progress.container = {style: {}, classList: {
    add: v => classes.add(v), remove: v => classes.delete(v),
    toggle: (v, on) => on ? classes.add(v) : classes.delete(v),
  }};
  progress.bar = {style: {}};
  progress.text = {textContent: ''};
  return {progress, classes};
}

test('fast frame change never displays a loading overlay', t => {
  const {progress, classes} = loader(t);
  progress.showDeferred('next frame');
  t.mock.timers.tick(100);
  progress.hide();
  t.mock.timers.tick(1000);
  assert.equal(progress.container.style.display, 'none');
  assert.equal(classes.has('hidden'), true);
});

test('slow frame change displays only delayed nonblocking feedback', t => {
  const {progress, classes} = loader(t);
  progress.showDeferred('next frame');
  t.mock.timers.tick(299);
  assert.equal(progress.container.style.display, 'none');
  t.mock.timers.tick(1);
  assert.equal(classes.has('nonblocking'), true);
  assert.equal(classes.has('hidden'), false);
  assert.equal(progress.text.textContent, 'next frame');
});

test('new frame request cancels an older pending loading message', t => {
  const {progress} = loader(t);
  progress.showDeferred('old');
  t.mock.timers.tick(200);
  progress.showDeferred('new');
  t.mock.timers.tick(100);
  assert.equal(progress.container.style.display, 'none');
  t.mock.timers.tick(200);
  assert.equal(progress.text.textContent, 'new');
});

test('waiting for another frame preserves existing scene, including on fetch failure', async t => {
  let finish;
  t.mock.method(globalThis, 'fetch', () => new Promise(resolve => {finish = resolve;}));
  t.mock.method(console, 'error', () => {});
  const viewer = new Viewer3D('unused');
  viewer._showDropOverlay = () => {};
  const original = new Viewer3D('unused').meshGroup;
  viewer.meshGroup.add(original);
  const loading = viewer.buildSceneFromVTU({format_version:'3.0', frames:[{vtu_file:'next.vtu'}]});
  assert.equal(viewer.meshGroup.children[0], original);
  finish({ok: false, status: 404});
  await assert.rejects(loading, /HTTP 404/);
  assert.equal(viewer.meshGroup.children[0], original);
});
