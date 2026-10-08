// Real exported ODB frames through the actual parser + Three.js scene builder.
// Headless CPU measurement; no WebGL upload, GPU timing or browser FPS claim.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {DOMParser} from 'linkedom';
import * as THREE from 'three';
import {Viewer3D} from '../src/viewer3d.js';
globalThis.DOMParser = DOMParser;
globalThis.fetch = async url => ({ok:true,text:() => fs.readFile(fileURLToPath(url),'utf8')});
const cases = [];
for (const file of process.argv.slice(2)) {
  const model = JSON.parse(await fs.readFile(file,'utf8'));
  model._baseUrl = pathToFileURL(path.resolve(file)).href;
  // Use one real final frame, preventing asynchronous prefetch from polluting timings.
  model.frames = [model.frames.at(-1)];
  const viewer = new Viewer3D('unused');
  viewer.scene = new THREE.Scene(); viewer.renderer = {};
  viewer._showDropOverlay = () => {}; viewer._fitCamera = () => {};
  const field = model.fields.find(f => f.name === 'S_mises');
  await viewer.buildSceneFromVTU(model,{field});
  const cold = {...viewer.lastTimings};
  const warm = [];
  for (let i=0;i<5;i++) {
    await viewer.buildSceneFromVTU(model,{field,preserveCamera:true,deformed:true,scaleFactor:1+i*.1});
    warm.push({...viewer.lastTimings});
  }
  cases.push({source:path.resolve(file),nodes:model.num_nodes,cold,warm,rssBytes:process.memoryUsage().rss});
  viewer.clearResult();
}
process.stdout.write(JSON.stringify({scope:'Real VTU, Node CPU parse and scene buffer update; excludes browser/GPU',cases},null,2));
