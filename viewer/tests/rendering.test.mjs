import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {Viewer3D} from '../src/viewer3d.js';
import {guardDragClicks} from '../src/gestures.js';

test('rotation drag suppresses picking, while ordinary clicks still reach tools', () => {
  const canvas = new EventTarget();
  const unbind = guardDragClicks(canvas);
  let picked = 0;
  canvas.addEventListener('click', () => picked++);
  const send = (name, x, y) => canvas.dispatchEvent(Object.assign(
    new Event(name, {cancelable:true}), {clientX:x,clientY:y}));
  send('pointerdown', 10, 10);
  send('pointermove', 100, 20);
  send('pointerup', 10, 10); // Returning to the start is still a drag.
  assert.equal(send('click',10,10), false);
  assert.equal(picked, 0);
  send('pointerdown', 10, 10);
  send('pointerup', 12, 11);
  send('click',12,11);
  assert.equal(picked, 1);
  send('pointerdown', 10, 10);
  send('pointercancel', 10, 10);
  unbind();
  send('click',10,10);
  assert.equal(picked, 2);
});

test('idle frames skip GPU work; camera and display changes repaint once', t => {
  const originalRAF = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => 1;
  t.after(() => {
    if (originalRAF) globalThis.requestAnimationFrame = originalRAF;
    else delete globalThis.requestAnimationFrame;
  });
  const viewer = new Viewer3D('unused');
  let draws = 0, samples = 0, moved = false;
  viewer.scene = new THREE.Scene();
  viewer.renderer = {render: () => draws++};
  viewer.controls = {update: () => {samples++; if (moved) viewer.requestRender();}};
  viewer._animate();
  for (let i = 0; i < 120; i++) viewer._animate();
  assert.equal(draws, 1);
  assert.equal(samples, 121); // New input must still be sampled while idle.
  moved = true;
  viewer._animate();
  assert.equal(draws, 2);
  moved = false;
  for (const change of [() => viewer.setWireframe(true), () => viewer.setOpacity(.5),
    () => viewer.setClippingEnabled(true), () => viewer.clearResult()]) {
    const before = draws;
    change();
    viewer._animate();
    viewer._animate();
    assert.equal(draws, before + 1);
  }
});

test('container resize updates projection, drawing size and pointer mapping together', () => {
  const viewer = new Viewer3D('unused');
  let width = 640, height = 480, mapped = 0, resized;
  viewer.container = {getBoundingClientRect: () => ({width,height})};
  viewer.camera = new THREE.PerspectiveCamera();
  viewer.renderer = {setSize: (w,h) => {resized = [w,h];}};
  viewer.controls = {handleResize: () => mapped++};
  viewer._needsRender = false;
  viewer._onResize();
  assert.deepEqual(resized, [640,480]);
  assert.equal(viewer.camera.aspect, 640 / 480);
  assert.equal(mapped, 1);
  assert.equal(viewer._needsRender, true);
  width = 900;
  viewer._onResize();
  assert.deepEqual(resized, [900,480]);
  assert.equal(mapped, 2);
  height = 0;
  viewer._onResize();
  assert.equal(mapped, 2); // Hidden containers must not produce an invalid camera.
});
