import {test} from 'node:test';
import assert from 'node:assert/strict';
import {colormapToCSS, getColormapNames} from '../src/colormaps.js';
import {UIController} from '../src/ui.js';

test('all color ramps use CSS color-before-position stops', () => {
  for (const name of getColormapNames()) {
    const css = colormapToCSS(name);
    assert.match(css, /^linear-gradient\(to right, rgb\(\d+,\d+,\d+\) 0%/);
    assert.match(css, /rgb\(\d+,\d+,\d+\) 100%\)$/);
    assert.doesNotMatch(css, /% rgb/);
  }
});

function renderLegend(t, values, field = {label: 'Stress (mises)', name: 'S_mises'}) {
  const elements = new Map();
  const old = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', {configurable: true, value: {getElementById(id) {
    if (!elements.has(id)) {
      const classes = new Set(['hidden']);
      elements.set(id, {textContent: '', style: {}, classList: classes});
      classes.remove = classes.delete.bind(classes);
    }
    return elements.get(id);
  }}});
  t.after(() => old ? Object.defineProperty(globalThis, 'document', old) : delete globalThis.document);
  UIController.prototype._updateLegend.call({
    state: {data: {}, currentField: field, format: 'v3.0', colormapName: 'jet'},
    viewer: {_lastVtuResult: {fieldValues: values}},
    _contourCustomMin: null, _contourCustomMax: null,
  });
  return id => elements.get(id);
}

test('uniform contact stress shows 10 and same-color legend', t => {
  const el = renderLegend(t, Array(16).fill(10));
  assert.equal(el('legend').classList.has('hidden'), false);
  assert.equal(el('legend-min').textContent, '10');
  assert.equal(el('legend-max').textContent, '10');
  assert.match(el('legend-bar').style.background, /^rgb\(/);
  assert.match(el('legend-note').textContent, /全场同值/);
});

test('nonuniform data shows minimum midpoint and maximum', t => {
  const el = renderLegend(t, [-10, -5, 0, NaN, Infinity]);
  assert.equal(el('legend-min').textContent, '-10');
  assert.equal(el('legend-mid').textContent, '-5');
  assert.match(el('legend-bar').style.background, /^linear-gradient/);
});

test('missing data does not invent a zero-to-one stress range', t => {
  const el = renderLegend(t, [NaN, Infinity]);
  assert.equal(el('legend-min').textContent, '—');
  assert.equal(el('legend-note').textContent, '当前帧无有效数据');
});

test('no selected field keeps legend hidden', t => {
  const el = renderLegend(t, [], null);
  assert.equal(el('legend').classList.has('hidden'), true);
});
