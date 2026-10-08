// Synthetic disconnected hexes: full ASCII parser + CPU scene buffers, not GPU.
import {DOMParser} from 'linkedom';
import * as THREE from 'three';
import {parseVTU} from '../src/vtuparser.js';
import {Viewer3D} from '../src/viewer3d.js';
globalThis.DOMParser = DOMParser;
const cases = [];
for (const nodes of [10_000,100_000,1_000_000]) {
  const corners = [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]];
  const count = nodes/8;
  let xml = `<VTKFile type="UnstructuredGrid"><UnstructuredGrid><Piece><Points><DataArray NumberOfComponents="3">${Array.from({length:nodes},(_,i)=>{const c=corners[i%8];return `${Math.floor(i/8)*2+c[0]} ${c[1]} ${c[2]}`;}).join(' ')}</DataArray></Points><Cells><DataArray Name="connectivity">${Array.from({length:nodes},(_,i)=>i).join(' ')}</DataArray><DataArray Name="offsets">${Array.from({length:count},(_,i)=>(i+1)*8).join(' ')}</DataArray><DataArray Name="types">${'12 '.repeat(count)}</DataArray></Cells><PointData><DataArray Name="S">${'1 '.repeat(nodes)}</DataArray></PointData></Piece></UnstructuredGrid></VTKFile>`;
  const start = performance.now();
  let parsed = parseVTU(xml);
  const parseMs = performance.now()-start;
  xml = null;
  const viewer = new Viewer3D('unused');
  viewer.scene = new THREE.Scene();viewer.renderer = {};viewer._showDropOverlay=()=>{};viewer._fitCamera=()=>{};
  await viewer.buildSceneFromVTU(parsed);
  const coldBuildMs = viewer.lastBuildMs;
  await viewer.buildSceneFromVTU(parsed,{preserveCamera:true});
  cases.push({nodes,cells:count,parseMs,coldBuildMs,reusedBuildMs:viewer.lastBuildMs,
    reusedGeometry:viewer.lastTimings.reusedGeometry,rssBytes:process.memoryUsage().rss});
  viewer.clearResult();parsed=null;globalThis.gc?.();
}
process.stdout.write(JSON.stringify({scope:'Synthetic full ASCII parse and CPU buffers, excludes GPU and solver',cases},null,2));
