/**
 * VTK/VTP XML PolyData parser.
 * Parses the ASCII VTK XML PolyData format used in model v2.0.
 *
 * VTP structure:
 *   <VTKFile type="PolyData">
 *     <PolyData>
 *       <Piece NumberOfPoints="N" NumberOfPolys="M">
 *         <PointData>
 *           <DataArray type="Float64" Name="S_Mises">...</DataArray>
 *           <DataArray type="Float64" Name="U" NumberOfComponents="3">...</DataArray>
 *         </PointData>
 *         <Points>
 *           <DataArray type="Float64" Name="Points" NumberOfComponents="3">...</DataArray>
 *         </Points>
 *         <Polys>
 *           <DataArray type="Int32" Name="connectivity">tri indices...</DataArray>
 *           <DataArray type="Int32" Name="offsets">cumulative counts...</DataArray>
 *         </Polys>
 *       </Piece>
 *     </PolyData>
 *   </VTKFile>
 */

export class VTKParsedData {
  constructor() {
    /** @type {Float64Array} Flat [x,y,z, x,y,z, ...] */
    this.points = null;
    /** @type {Uint32Array} Triangle indices */
    this.triangles = null;
    /** @type {Object<string, Float64Array>} Point data arrays keyed by name */
    this.pointData = {};
    /** @type {number} Number of points */
    this.numPoints = 0;
    /** @type {number} Number of triangles */
    this.numPolys = 0;
  }
}

/**
 * Parse a VTP XML string into a VTKParsedData object.
 * Handles ASCII format DataArrays.
 */
export function parseVTP(xmlText) {
  const data = new VTKParsedData();

  // Extract NumberOfPoints and NumberOfPolys
  const pieceMatch = xmlText.match(/<Piece\s+NumberOfPoints="(\d+)"[^>]*NumberOfPolys="(\d+)"/);
  if (!pieceMatch) throw new Error('Cannot find Piece element in VTP');
  data.numPoints = parseInt(pieceMatch[1], 10);
  data.numPolys = parseInt(pieceMatch[2], 10);

  // Extract Points
  const pointsMatch = xmlText.match(/<Points>[\s\S]*?<DataArray[^>]*>([\s\S]*?)<\/DataArray>[\s\S]*?<\/Points>/);
  if (!pointsMatch) throw new Error('Cannot find Points in VTP');
  data.points = parseFloat64Array(pointsMatch[1], 3, data.numPoints);

  // Extract Polys: connectivity + offsets
  const polysSection = xmlText.match(/<Polys>([\s\S]*?)<\/Polys>/);
  if (!polysSection) throw new Error('Cannot find Polys in VTP');
  const polysText = polysSection[1];

  const connMatch = polysText.match(/<DataArray[^>]*Name="connectivity"[^>]*>([\s\S]*?)<\/DataArray>/);
  const offsMatch = polysText.match(/<DataArray[^>]*Name="offsets"[^>]*>([\s\S]*?)<\/DataArray>/);
  if (!connMatch || !offsMatch) throw new Error('Missing connectivity or offsets in Polys');

  const connectivity = parseInt32Array(connMatch[1]);
  const offsets = parseInt32Array(offsMatch[1]);

  // Convert from VTK polys (offsets-based) to flat triangle array
  // Each offset gives the end of a polygon's indices
  let prevOffset = 0;
  const triIndices = [];
  for (let i = 0; i < offsets.length; i++) {
    const off = offsets[i];
    const verts = [];
    for (let j = prevOffset; j < off; j++) {
      verts.push(connectivity[j]);
    }
    prevOffset = off;
    if (verts.length === 3) {
      triIndices.push(verts[0], verts[1], verts[2]);
    } else if (verts.length > 3) {
      // Fan triangulation for quads/polygons
      for (let k = 1; k < verts.length - 1; k++) {
        triIndices.push(verts[0], verts[k], verts[k + 1]);
      }
    }
  }
  data.triangles = new Uint32Array(triIndices);
  data.numPolys = triIndices.length / 3;

  // Extract PointData arrays
 const pointDataSection = xmlText.match(/<PointData>([\s\S]*?)<\/PointData>/);
 if (pointDataSection) {
   const pdText = pointDataSection[1];
   const arrayRegex = /<DataArray[^>]*Name="([^"]*)"[^>]*>([\s\S]*?)<\/DataArray>/g;
   let match;
   while ((match = arrayRegex.exec(pdText)) !== null) {
     const name = match[1];
     const rawText = match[2].trim();

     // Determine number of components from attribute
     const headerMatch = match[0].match(/NumberOfComponents="(\d+)"/);
     const nComp = headerMatch ? parseInt(headerMatch[1], 10) : 1;

     // Check type
     const isFloat = /type="Float(32|64)"/.test(match[0]);

     if (nComp === 1) {
       data.pointData[name] = isFloat ? parseFloat64Array(rawText, 1, data.numPoints) : parseInt32Array(rawText, data.numPoints);
     } else {
       data.pointData[name] = parseFloat64Array(rawText, nComp, data.numPoints);
     }
   }
 }

  return data;
}

function parseFloat64Array(text, nComp, expectedCount) {
  const nums = text.trim().split(/[\s\n\r]+/).filter(s => s.length > 0).map(Number);
  return new Float64Array(nums);
}

function parseInt32Array(text, expectedCount) {
  const nums = text.trim().split(/[\s\n\r]+/).filter(s => s.length > 0).map(Number);
  return new Int32Array(nums);
}

/**
 * Fetch and parse a VTP file given its URL path relative to the model location.
 */
export async function loadVTP(vtpUrl, baseUrl) {
  const url = new URL(vtpUrl, baseUrl).href;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Failed to load VTP: ${resp.status} ${resp.statusText}`);
  const text = await resp.text();
  return parseVTP(text);
}
