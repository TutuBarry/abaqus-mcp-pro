import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sampleColormap} from '../src/colormaps.js';

test('missing scalar is shown in neutral grey', () => {
  assert.deepEqual(sampleColormap('jet', NaN), [0.55, 0.55, 0.55]);
});
import {triangulateCell, finiteRange} from '../src/vtuparser.js';

for (const [name, type, count, triangles] of [
  ['tetra',10,4,4], ['quad',9,4,2], ['hex',12,8,12], ['wedge',13,6,8],
  ['pyramid',14,5,6], ['S6',22,6,1], ['S8',23,8,2], ['S9',28,9,2],
  ['C3D10',24,10,4], ['C3D20',25,20,12], ['C3D15',26,15,8],
]) {
  test(name + ' uses its cell type', () => {
    const indices = [], lines = [];
    triangulateCell(Array.from({length:count},(_,i)=>i),type,indices,lines);
    assert.equal(indices.length / 3,triangles);
    assert.equal(lines.length,0);
  });
}
test('million node reduction has bounded stack use',()=> {
  assert.deepEqual(finiteRange(new Float64Array(1_000_000).fill(3)),{min:3,max:3,count:1_000_000});
});
test('missing values are excluded from scalar range',()=> {
  assert.deepEqual(finiteRange([NaN, Infinity, -2, 6]), {min:-2,max:6,count:2});
});
test('unsupported and malformed cells fail explicitly',()=> {
  assert.throws(()=>triangulateCell([0,1,2],10,[],[]));
  assert.throws(()=>triangulateCell([0,1,2],999,[],[]));
});
