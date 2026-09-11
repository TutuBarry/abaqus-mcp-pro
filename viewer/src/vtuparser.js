/**
 * VTK XML Unstructured Grid (ASCII) Parser.
 * Parses .vtu files into geometry and field data.
 * Supports UnstructuredGrid with cell type mapping to Three.js geometry.
 */

// VTK Cell Type → node count mapping
const VTK_CELL_NODES = {
  1: 1,   // VTK_VERTEX
  3: 2,   // VTK_LINE
  5: 3,   // VTK_TRIANGLE
  7: 5,   // VTK_PYRAMID
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
export function parseVTU(text) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, 'text/xml');
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

  // PointData Scalars
  let fieldValues = null;
  let fieldMin = 0;
  let fieldMax = 1;

  let pdEl = root.querySelector('PointData DataArray[NumberOfComponents="1"]');
  if (!pdEl) {
    pdEl = root.querySelector('PointData DataArray:not([NumberOfComponents])');
  }
  if (!pdEl) {
    pdEl = root.querySelector('PointData DataArray');
  }
  if (pdEl) {
    const nc = parseInt(pdEl.getAttribute('NumberOfComponents') || '1');
    if (nc === 1) {
      fieldValues = parseDataArray(pdEl);
    } else {
      const raw = parseDataArray(pdEl);
      fieldValues = [];
      for (let i = 0; i < raw.length; i += nc) {
        fieldValues.push(raw[i]);
      }
    }
    const valid = fieldValues.filter(v => v != null && !isNaN(v));
    if (valid.length > 0) {
      fieldMin = Math.min(...valid);
      fieldMax = Math.max(...valid);
    }
  }

  // Convert cells to triangle indices
  const indices = [];
  const cells = [];
  let cursor = 0;
  for (let i = 0; i < offsets.length; i++) {
    const end = offsets[i];
    const nVerts = end - cursor;
    const cell = [];
    for (let k = 0; k < nVerts; k++) {
      cell.push(connectivity[cursor + k]);
    }
    cells.push(cell);
    triangulateCell(cell, indices);
    cursor = end;
  }

  return { positions, indices, cells, cellTypes, fieldValues, fieldMin, fieldMax };
}

function triangulateCell(cell, indices) {
  const n = cell.length;
  if (n === 3) {
    indices.push(cell[0], cell[1], cell[2]);
  } else if (n === 4) {
    indices.push(cell[0], cell[1], cell[2]);
    indices.push(cell[0], cell[2], cell[3]);
  } else if (n === 5) {
    indices.push(cell[0], cell[1], cell[2]);
    indices.push(cell[0], cell[2], cell[3]);
    indices.push(cell[0], cell[1], cell[4]);
    indices.push(cell[1], cell[2], cell[4]);
    indices.push(cell[2], cell[3], cell[4]);
    indices.push(cell[3], cell[0], cell[4]);
  } else if (n === 6) {
    indices.push(cell[0], cell[1], cell[2]);
    indices.push(cell[3], cell[5], cell[4]);
    indices.push(cell[0], cell[3], cell[4]);
    indices.push(cell[0], cell[4], cell[1]);
    indices.push(cell[1], cell[4], cell[5]);
    indices.push(cell[1], cell[5], cell[2]);
    indices.push(cell[2], cell[5], cell[3]);
    indices.push(cell[2], cell[3], cell[0]);
  } else if (n === 8) {
    const f = [
      [0,1,2,3], [4,7,6,5],
      [0,4,5,1], [1,5,6,2],
      [2,6,7,3], [3,7,4,0],
    ];
    for (const face of f) {
      indices.push(cell[face[0]], cell[face[1]], cell[face[2]]);
      indices.push(cell[face[0]], cell[face[2]], cell[face[3]]);
    }
  } else if (n === 10) {
    indices.push(cell[0], cell[1], cell[2]);
    indices.push(cell[0], cell[2], cell[3]);
    indices.push(cell[1], cell[3], cell[2]);
    indices.push(cell[0], cell[3], cell[1]);
  } else if (n === 20 || n === 15) {
    const corners = n === 20 ? 8 : 6;
    const linear = cell.slice(0, corners);
    triangulateCell(linear, indices);
  } else {
    for (let i = 1; i < n - 1; i++) {
      indices.push(cell[0], cell[i], cell[i + 1]);
    }
  }
}

function parseDataArray(el) {
  const fmt = el.getAttribute('format') || 'ascii';
  if (fmt !== 'ascii') {
    throw new Error('Only ASCII format DataArray is supported. Found: ' + fmt);
  }
  const text = el.textContent.trim();
  return text.split(/\s+/).map(Number);
}

export async function loadVTU(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(HTTP );
  const text = await resp.text();
  return parseVTU(text);
}
