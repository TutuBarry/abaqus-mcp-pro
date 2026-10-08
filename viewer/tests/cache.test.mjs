import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DOMParser} from 'linkedom';
import * as THREE from 'three';
import {FrameCache} from '../src/framecache.js';
import {parseVTU, selectVTUField} from '../src/vtuparser.js';
import {Viewer3D} from '../src/viewer3d.js';
globalThis.DOMParser = DOMParser;
const xml = `<VTKFile type="UnstructuredGrid"><UnstructuredGrid><Piece><Points><DataArray NumberOfComponents="3">0 0 0 1 0 0 0 1 0</DataArray></Points><Cells><DataArray Name="connectivity">0 1 2</DataArray><DataArray Name="offsets">3</DataArray><DataArray Name="types">5</DataArray></Cells><PointData><DataArray Name="S">1 2 3</DataArray><DataArray Name="U" NumberOfComponents="3">1 0 0 1 0 0 1 0 0</DataArray></PointData></Piece></UnstructuredGrid></VTKFile>`;

test('parsed frame LRU reads once, shares concurrent requests, evicts least recently used', async () => {
  const cache = new FrameCache({maxFrames: 2});
  let reads = 0;
  const read = async () => {reads++; return {positions:new Float32Array(30)};};
  await Promise.all([cache.get('a',read),cache.get('a',read)]);
  assert.equal(reads,1);
  await cache.get('b',read);
  assert.equal((await cache.get('a',read)).hit,true);
  await cache.get('c',read);
  assert.equal(cache.entries.has('b'),false);
  assert.ok(cache.bytes <= cache.maxBytes);
});
test('oversized frames are not retained', async () => {
  const cache = new FrameCache({maxBytes: 100});
  await cache.get('a',async () => new Float64Array(100));
  assert.equal(cache.bytes,0);
});
test('scrubbing cancels other frame requests without aborting the selected prefetch', async () => {
  const cache = new FrameCache(); const finish = {}, signals = {};
  const read = key => signal => {signals[key]=signal; return new Promise(r => {finish[key]=r;});};
  const a = cache.get('a',read('a')), b = cache.get('b',read('b'));
  cache.cancelExcept('b'); finish.a({}); finish.b({});
  await assert.rejects(a,{name:'AbortError'}); await b;
  assert.equal(signals.a.aborted,true); assert.equal(signals.b.aborted,false);
  assert.deepEqual([...cache.entries.keys()],['b']);
});
test('reset aborts pending requests and prevents stale cache insertion', async () => {
  const cache = new FrameCache(); let finish, signal;
  const p = cache.get('a',s => {signal=s; return new Promise(r => {finish=r;});});
  cache.clear(); finish({positions:[]});
  await assert.rejects(p,{name:'AbortError'});
  assert.equal(signal.aborted,true); assert.equal(cache.entries.size,0);
});
test('field switching uses parsed arrays without mutating source coordinates', () => {
  const parsed = parseVTU(xml);
  assert.deepEqual([...selectVTUField(parsed,'U',0).fieldValues],[1,1,1]);
  assert.equal(selectVTUField(parsed,'S').pointFields,parsed.pointFields);
  assert.throws(() => selectVTUField(parsed,'missing'),/missing/);
  assert.throws(() => selectVTUField(parsed,'U',4),/component/);
});
test('frame updates reuse surface buffers and deformation never accumulates', async () => {
  const viewer = new Viewer3D('unused');
  viewer.renderer = {};
  viewer.scene = new THREE.Scene(); viewer._showDropOverlay = () => {}; viewer._fitCamera = () => {};
  const parsed = parseVTU(xml); parsed._metadata = {deformation_scale_factor:0};
  await viewer.buildSceneFromVTU({...parsed}, {deformed:true,scaleFactor:2});
  const geometry = viewer.meshGroup.children[0].geometry;
  assert.equal(geometry.attributes.position.array[0],2);
  await viewer.buildSceneFromVTU({...parsed}, {deformed:true,scaleFactor:3,preserveCamera:true});
  assert.equal(viewer.meshGroup.children[0].geometry,geometry);
  assert.equal(geometry.attributes.position.array[0],3);
  assert.equal(parsed.positions[0],0);
  assert.equal(viewer.lastTimings.reusedGeometry,true);
  await viewer.buildSceneFromVTU({...parsed}, {hiddenBodies:[0],preserveCamera:true});
  viewer.clearResult(); assert.equal(viewer.meshGroup.children.length,0);
});
test('compact frame parsing retains element count and line buffers update in place', async () => {
  const lineXml = xml.replace('0 1 2</DataArray><DataArray Name="offsets">3','0 1</DataArray><DataArray Name="offsets">2').replace('Name="types">5','Name="types">3');
  const parsed = parseVTU(lineXml,{retainCells:false});
  assert.equal(parsed.cells,null); assert.equal(parsed.cellCount,1);
  const viewer = new Viewer3D('unused'); viewer.scene=new THREE.Scene();viewer.renderer={};
  viewer._showDropOverlay=()=>{};viewer._fitCamera=()=>{};
  await viewer.buildSceneFromVTU(parsed);
  const geom = viewer._lineGroup.children[0].geometry;
  await viewer.buildSceneFromVTU({...parsed,positions:Float32Array.from(parsed.positions,v=>v+1)}, {preserveCamera:true});
  assert.equal(viewer._lineGroup.children[0].geometry,geom);
  assert.equal(geom.attributes.position.array[0],1);
  assert.equal(viewer.getVtuStats().elements,1);
  viewer.clearResult();
});
