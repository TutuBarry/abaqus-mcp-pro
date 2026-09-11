/**
 * VTK XML PolyData (ASCII) parser.
 * Parses .vtp files into geometry data usable by Viewer3D.
 *
 * Supports:
 * - VTKFile type="PolyData" (legacy XML format)
 * - ASCII format only (base64 not yet supported)
 * - PointData Scalars (for field values)
 * - Points + Polys (triangles/quads)
 */

/**
 * Parse a VTK XML PolyData string.
 * @param {string} text - VTP file content
 * @returns {object} { positions, indices, fieldValues, fieldMin, fieldMax }
 */
export function parseVTP(text) {
  const doc = new DOMParser().parseFromString(text, 'text/xml');
  const root = doc.documentElement;

  if (root.getAttribute('type') !== 'PolyData') {
    throw new Error('Only PolyData type is supported');
  }

  // ── Points ──
  const pointsEl = root.querySelector('Points DataArray');
  if (!pointsEl) throw new Error('No Points DataArray found');
  const ptsRaw = parseDataArray(pointsEl);
  const positions = [];
  for (let i = 0; i < ptsRaw.length; i += 3) {
    positions.push(ptsRaw[i], ptsRaw[i + 1], ptsRaw[i + 2]);
  }

  // ── Polys (connectivity + offsets) ──
  let indices = [];
  const polysEl = root.querySelector('Polys');
  if (polysEl) {
    const connEl = polysEl.querySelector('DataArray[Name="connectivity"]');
    const offsetsEl = polysEl.querySelector('DataArray[Name="offsets"]');
    if (connEl && offsetsEl) {
      const conn = parseDataArray(connEl);
      const offsets = parseDataArray(offsetsEl);
      let cursor = 0;
      for (let i = 0; i < offsets.length; i++) {
        const end = offsets[i];
        const nVerts = end - cursor;
        const face = [];
        for (let k = 0; k < nVerts; k++) face.push(conn[cursor + k]);
        // Triangulate
        if (nVerts === 3) {
          indices.push(face[0], face[1], face[2]);
        } else if (nVerts === 4) {
          indices.push(face[0], face[1], face[2]);
          indices.push(face[0], face[2], face[3]);
        } else {
          for (let k = 1; k < nVerts - 1; k++) {
            indices.push(face[0], face[k], face[k + 1]);
          }
        }
        cursor = end;
      }
    }
  }

  // ── PointData Scalars ──
  let fieldValues = null;
  let fieldMin = 0;
  let fieldMax = 1;
  const pdScalars = root.querySelector('PointData DataArray[NumberOfComponents="1"]');
  if (pdScalars) {
    fieldValues = parseDataArray(pdScalars);
    const valid = fieldValues.filter(v => v !== null && v !== undefined && !isNaN(v));
    if (valid.length > 0) {
      fieldMin = Math.min(...valid);
      fieldMax = Math.max(...valid);
    }
  }

  return { positions, indices, fieldValues, fieldMin, fieldMax };
}

/**
 * Parse a VTK DataArray element containing ASCII numbers.
 */
function parseDataArray(el) {
  const fmt = el.getAttribute('format') || 'ascii';
  if (fmt !== 'ascii') {
    throw new Error('Only ASCII format DataArray is supported');
  }
  const text = el.textContent.trim();
  return text.split(/\s+/).map(Number);
}

/**
 * Create VTP content from geometry data (for export).
 * @param {number[]} positions - flat [x,y,z,...]
 * @param {number[]} indices - triangle indices
 * @param {number[]} [fieldValues] - per-node scalar values
 * @returns {string} VTP XML text
 */
export function createVTP(positions, indices, fieldValues) {
  const nPts = positions.length / 3;
  if (!Number.isInteger(nPts) || nPts === 0) throw new Error('Invalid positions array');
  const nPolys = indices.length / 3;
  if (!Number.isInteger(nPolys) || nPolys === 0) throw new Error('Invalid indices array');

  // Build connectivity array (list of vertex indices per poly)
  const conn = [];
  const offsets = [];
  for (let i = 0; i < nPolys; i++) {
    const base = i * 3;
    conn.push(indices[base], indices[base + 1], indices[base + 2]);
    offsets.push(conn.length);
  }

  const fmt = (v) => {
    if (Number.isInteger(v)) return v.toString();
    if (Math.abs(v) < 1e-10 && v !== 0) return v.toExponential(8);
    return v.toFixed(8).replace(/\.?0+$/, '');
  };

  let xml = `<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
  <PolyData>
    <Piece NumberOfPoints="${nPts}" NumberOfVerts="0" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="${nPolys}">
      <Points>
        <DataArray type="Float32" NumberOfComponents="3" format="ascii">
${positions.map(v => fmt(v)).join(' ')}
        </DataArray>
      </Points>`;

  if (fieldValues) {
    xml += `
      <PointData Scalars="field">
        <DataArray type="Float32" Name="field" NumberOfComponents="1" format="ascii">
${fieldValues.map(v => fmt(v)).join(' ')}
        </DataArray>
      </PointData>`;
  }

  xml += `
      <Polys>
        <DataArray type="Int32" Name="connectivity" format="ascii">
${conn.join(' ')}
        </DataArray>
        <DataArray type="Int32" Name="offsets" format="ascii">
${offsets.join(' ')}
        </DataArray>
      </Polys>
    </Piece>
  </PolyData>
</VTKFile>`;

  return xml;
}


/**
 * Extract just the scalar values and positions from a VTP parse result
 * for use as a per-frame data source in v2.0 format.
 * Returns an object compatible with the Viewer3D._buildGeom expectations.
 */
export function vtpToFrameData(vtpResult, fieldMin, fieldMax) {
  return {
    positions: vtpResult.positions,
    indices: vtpResult.indices,
    fieldValues: vtpResult.fieldValues,
    fieldMin: fieldMin !== undefined ? fieldMin : vtpResult.fieldMin,
    fieldMax: fieldMax !== undefined ? fieldMax : vtpResult.fieldMax,
  };
}
