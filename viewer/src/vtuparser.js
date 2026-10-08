/**
 * VTK XML Unstructured Grid (ASCII) Parser — handles mesh + line primitives.
 * Parses .vtu files into geometry (indices for surfaces, lines for beams/trusses) and field data.
 * Supports UnstructuredGrid with cell type mapping to Three.js geometry.
 */

// VTK Cell Type → node count mapping
const VTK_CELL_NODES = {
  1: 1,   // VTK_VERTEX
  3: 2,   // VTK_LINE
  5: 3,   // VTK_TRIANGLE
  14: 5,  // VTK_PYRAMID
  9: 4,   // VTK_QUAD
  10: 4,  // VTK_TETRA
  12: 8,  // VTK_HEXAHEDRON
  13: 6,  // VTK_WEDGE
  21: 3,  // VTK_QUADRATIC_EDGE
  22: 6,  // VTK_QUADRATIC_TRIANGLE
  23: 8,  // VTK_QUADRATIC_QUAD
  24: 10, // VTK_QUADRATIC_TETRA
  25: 20, // VTK_QUADRATIC_HEXAHEDRON
  26: 15, // VTK_QUADRATIC_WEDGE
};

/**
 * Parse a VTK XML UnstructuredGrid string.
 * @param {string} text - VTU file content
 * @returns {object} { positions, indices, cellTypes, fieldValues, fieldMin, fieldMax }
 */
/**
 * Parse a VTK XML UnstructuredGrid string.
 * Optionally select a specific field by name.
 * @param {string} text - VTU file content
 * @param {object} options
 * @param {string} options.fieldName - exact Name attribute to select (optional)
 * @returns {object} { positions, indices, lines, cells, cellTypes, fieldValues, fieldMin, fieldMax, vectorFields }
 */
export function parseVTU(text, options = {}) {
  const { fieldName, componentIndex = 0, retainCells = true } = options;
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, 'text/xml');
  if (doc.querySelector('parsererror')) throw new Error('Invalid VTU XML');
  const root = doc.documentElement;

  if (root.getAttribute('type') !== 'UnstructuredGrid') {
    throw new Error('Only UnstructuredGrid type is supported');
  }

  // Points
  const pointsEl = root.querySelector('Points DataArray');
  if (!pointsEl) throw new Error('No Points DataArray found');
  const ptsRaw = parseDataArray(pointsEl);
  const positions = [];
  for (let i = 0; i < ptsRaw.length; i += 3) {
    positions.push(ptsRaw[i], ptsRaw[i + 1], ptsRaw[i + 2]);
  }

  // Cells
  const cellsEl = root.querySelector('Cells');
  let connectivity = [];
  let offsets = [];
  let cellTypes = [];

  if (cellsEl) {
    const connEl = cellsEl.querySelector('DataArray[Name="connectivity"]');
    const offsetsEl = cellsEl.querySelector('DataArray[Name="offsets"]');
    const typesEl = cellsEl.querySelector('DataArray[Name="types"]');
    if (connEl && offsetsEl && typesEl) {
      connectivity = parseDataArray(connEl);
      offsets = parseDataArray(offsetsEl);
      cellTypes = parseDataArray(typesEl);
    }
  }

  const pointFields = Object.create(null), vectorFields = Object.create(null);
  root.querySelectorAll('PointData DataArray').forEach(arr => {
    const name = arr.getAttribute('Name');
    const ncomp = Number(arr.getAttribute('NumberOfComponents') || 1);
    if (!Number.isInteger(ncomp) || ncomp < 1) throw new Error('Invalid component count');
    const values = new Float64Array(parseDataArray(arr));
    if (values.length !== positions.length / 3 * ncomp) throw new Error('Field/node count mismatch');
    if (name) {
      pointFields[name] = {values, ncomp};
      if (ncomp > 1) vectorFields[name] = pointFields[name];
    }
  });
  if (positions.some(v => !Number.isFinite(v))) throw new Error('Non-finite geometry');
  if (offsets.length !== cellTypes.length || (offsets.length && offsets.at(-1) !== connectivity.length)) {
    throw new Error('Invalid cell offsets');
  }

  // Convert cells to triangle indices and line segments
  const indices = [];
  const lines = [];
  const cells = [];
  let cursor = 0;
  for (let i = 0; i < offsets.length; i++) {
    const end = offsets[i];
    const nVerts = end - cursor;
    const cellType = cellTypes[i];
    const cell = [];
    for (let k = 0; k < nVerts; k++) {
      cell.push(connectivity[cursor + k]);
    }
    if (end <= cursor || cell.some(v => !Number.isInteger(v) || v < 0 || v >= positions.length / 3)) {
      throw new Error('Invalid cell connectivity');
    }
    if (retainCells) cells.push(cell);
    triangulateCell(cell, cellType, indices, lines);
    cursor = end;
  }

  return selectVTUField({positions: new Float32Array(positions), indices: new Uint32Array(indices),
    lines: new Uint32Array(lines), cells: retainCells ? cells : null, cellCount: offsets.length,
    cellTypes: new Uint8Array(cellTypes), vectorFields, pointFields}, fieldName, componentIndex);
}

// Return a shallow view; cached coordinates and fields are never modified by deformation.
export function selectVTUField(parsed, fieldName, componentIndex = 0) {
  const fields = parsed.pointFields || {};
  const selectedName = fieldName || Object.keys(fields).find(k => fields[k].ncomp === 1) || Object.keys(fields)[0];
  const selected = fields[selectedName];
  if (fieldName && !selected) throw new Error('Requested field missing: ' + fieldName);
  let fieldValues = null;
  if (selected) {
    if (!Number.isInteger(componentIndex) || componentIndex < 0 || componentIndex >= selected.ncomp) throw new Error('Invalid field component index');
    fieldValues = selected.ncomp === 1 ? selected.values : Float64Array.from(
      {length: selected.values.length / selected.ncomp}, (_, i) => selected.values[i * selected.ncomp + componentIndex]);
  }
  const range = finiteRange(fieldValues || []);
  return {...parsed, fieldValues, fieldMin: range.min, fieldMax: range.max};
}

export function finiteRange(values) {
  let min = Infinity, max = -Infinity, count = 0;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    min = Math.min(min, value);
    max = Math.max(max, value);
    count++;
  }
  return { min: count ? min : 0, max: count ? max : 1, count };
}

export function filterSurfaceIndices(indices, bodyIds, hiddenBodies, fieldValues, contactOnly) {
  const hidden = new Set(hiddenBodies);
  if (!hidden.size && !contactOnly) return indices;
  const selected = [];
  for (let i = 0; i < indices.length; i += 3) {
    const tri = indices.slice(i, i + 3);
    if (tri.some(n => hidden.has(bodyIds[n]))) continue;
    if (contactOnly && tri.some(n => !Number.isFinite(fieldValues?.[n]))) continue;
    selected.push(...tri);
  }
  return selected;
}

// High-order cells are explicitly linearized using their corner nodes.
export function triangulateCell(cell, cellType, indices, lines) {
  const required = {1:1, 3:2, 21:3, 5:3, 22:6, 9:4, 23:8, 28:9,
                    10:4, 24:10, 12:8, 25:20, 13:6, 26:15, 14:5};
  if (!required[cellType] || cell.length !== required[cellType]) {
    throw new Error('Unsupported or malformed VTK cell type: ' + cellType);
  }
  if (cellType === 1) return;
  if (cellType === 3 || cellType === 21) {
    lines.push(cell[0], cell[1]);
    return;
  }
  let faces;
  if ([5, 22].includes(cellType)) faces = [[0,1,2]];
  else if ([9,23,28].includes(cellType)) faces = [[0,1,2,3]];
  else if ([10,24].includes(cellType)) faces = [[0,2,1],[0,1,3],[1,2,3],[2,0,3]];
  else if ([12,25].includes(cellType)) faces = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]];
  else if ([13,26].includes(cellType)) faces = [[0,2,1],[3,4,5],[0,1,4,3],[1,2,5,4],[2,0,3,5]];
  else faces = [[0,3,2,1],[0,1,4],[1,2,4],[2,3,4],[3,0,4]];
  for (const face of faces) {
    for (let j = 1; j < face.length - 1; j++) indices.push(cell[face[0]], cell[face[j]], cell[face[j+1]]);
  }
}

function parseDataArray(el) {
  const fmt = el.getAttribute('format') || 'ascii';
  if (fmt !== 'ascii') {
    throw new Error('Only ASCII format DataArray is supported. Found: ' + fmt);
  }
  const text = el.textContent.trim();
  return text ? text.split(/\s+/).map(Number) : [];
}

export async function loadVTU(url, options = {}) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  const text = await resp.text();
  return parseVTU(text, options);
}
