// CPU geometry conversion only; these figures do not measure browser/GPU rendering.
import {performance} from 'node:perf_hooks';
import {triangulateCell, finiteRange} from '../src/vtuparser.js';
const cases = [];
for (const cells of [1000, 10000, 100000]) {
  const start = performance.now();
  const triangles = [], lines = [];
  for (let i = 0; i < cells; i++) triangulateCell(Array.from({length:8}, (_,j)=>i*8+j), 12, triangles, lines);
  const range = finiteRange(new Float64Array(cells*8).fill(10));
  cases.push({cells, nodes: cells*8, triangles: triangles.length/3,
    elapsed_ms: performance.now()-start, rss_bytes: process.memoryUsage().rss, range});
}
process.stdout.write(JSON.stringify({scope:'Node CPU triangulation/reduction; synthetic disconnected hexes, not GPU or solver', cases}, null, 2));
