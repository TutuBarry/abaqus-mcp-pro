import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DOMParser} from 'linkedom';
import * as THREE from 'three';
import {parseVTU} from '../src/vtuparser.js';
import {Viewer3D} from '../src/viewer3d.js';
import {featureEdges, contourCoordinates, createContourMaterial, configureContour, bandedColormapCSS} from '../src/contours.js';
globalThis.DOMParser=DOMParser;
function fixture(points,cells,offsets,types) {
  return `<VTKFile type="UnstructuredGrid"><UnstructuredGrid><Piece><Points><DataArray>${points}</DataArray></Points><Cells><DataArray Name="connectivity">${cells}</DataArray><DataArray Name="offsets">${offsets}</DataArray><DataArray Name="types">${types}</DataArray></Cells></Piece></UnstructuredGrid></VTKFile>`;
}
const quad=fixture('0 0 0 1 0 0 1 1 0 0 1 0','0 1 2 3','4','9');
test('quad perimeter contains four edges and no artificial diagonal',()=>{
  const parsed=parseVTU(quad);
  assert.equal(parsed.indices.length,6);
  assert.equal(parsed.meshEdges.length,8);
  assert.equal(featureEdges(parsed.positions,parsed.indices).length,8);
});
test('internal solid faces are removed without changing cell counts',()=>{
  const p=parseVTU(fixture('0 0 0 1 0 0 0 1 0 0 0 1 0 0 -1','0 1 2 3 0 2 1 4','4 8','10 10'));
  assert.equal(p.cellCount,2);
  assert.equal(p.indices.length,18); // six exterior triangles, shared face excluded
  for(let i=0;i<p.indices.length;i+=3)
    assert.notDeepEqual([...p.indices.slice(i,i+3)].sort(),[0,1,2]);
});
test('feature edges retain creases and do not merge coincident disconnected parts',()=>{
  assert.equal(featureEdges(new Float32Array([0,0,0,1,0,0,0,1,0,0,0,1]),[0,1,2,0,3,1]).length,10);
  const p=parseVTU(fixture('0 0 0 1 0 0 0 1 0 0 0 0 1 0 0 0 1 0','0 1 2 3 4 5','3 6','5 5'));
  assert.equal(featureEdges(p.positions,p.indices).length,12);
});
test('scalar normalization retains out-of-range values until fragment clipping',()=>{
  assert.deepEqual([...contourCoordinates([-5,5,15,NaN],4,0,10)],[-.5,1,.5,1,1.5,1,0,0]);
  assert.deepEqual([...contourCoordinates([4],1,4,4)],[.5,1]);
  const material=createContourMaterial();
  configureContour(material,true,'spectrum',12);
  assert.equal(material.toneMapped,false);
  assert.equal(material.userData.contour.bands.value,12);
  assert.match(bandedColormapCSS('spectrum',12),/100%/);
  material.dispose();
});
test('edge positions, clipping and body visibility follow the displayed mesh',async()=>{
  const viewer=new Viewer3D('unused');viewer.scene=new THREE.Scene();viewer.renderer={};
  viewer._showDropOverlay=()=>{};viewer._fitCamera=()=>{};
  const parsed=parseVTU(quad);
  parsed._metadata={body_ids:[0,0,0,0]};
  await viewer.buildSceneFromVTU(parsed);
  const mesh=viewer.meshGroup.children[0];
  assert.equal(viewer.edgeGroup.children[0].geometry.attributes.position,mesh.geometry.attributes.position);
  assert.equal(viewer.wireframeGroup.children[0].geometry.index.count,8);
  viewer.setClippingEnabled(true);
  assert.equal(viewer.edgeGroup.children[0].material.clippingPlanes[0],viewer.clipPlane);
  const next={...parsed,positions:Float32Array.from(parsed.positions,v=>v+2)};
  await viewer.buildSceneFromVTU(next,{preserveCamera:true});
  assert.equal(viewer.edgeGroup.children[0].geometry.attributes.position.array[0],2);
  await viewer.buildSceneFromVTU(next,{hiddenBodies:[0],preserveCamera:true});
  assert.equal(viewer.edgeGroup.children.length,0);
  assert.equal(viewer.wireframeGroup.children.length,0);
});
