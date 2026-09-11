/**
 * ODB export API client.
 * Communicates with the Python serve_viewer.py backend.
 */

let exportedJsonPath = null;

/**
 * Request ODB export from the server.
 * @param {string} odbPath - Path to .odb file
 * @param {object} opts - Export options
 * @returns {Promise<object>} Export result
 */
export async function exportFromODB(odbPath, opts = {}) {
  const { step_index = -1, frame_step = 1, deformation_scale = 1.0, export_v2 = false } = opts;
 
  const resp = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      odb_path: odbPath,
      step_index,
      frame_step,
      deformation_scale,
      export_v2,
    }),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || `HTTP ${resp.status}`);
  }

  const result = await resp.json();

  if (!result.ok) {
    throw new Error(result.error || 'Export failed');
  }

  exportedJsonPath = result.output_path;
  return result;
}

/**
 * Get the path to the last exported JSON file.
 */
export function getExportedJsonPath() {
  return exportedJsonPath;
}

/**
 * Load the exported JSON file from the server.
 */
export async function loadExportedJson() {
  if (!exportedJsonPath) throw new Error('No exported file');
  const fname = exportedJsonPath.split(/[\\/]/).pop();
  const resp = await fetch('/' + fname);
  if (!resp.ok) throw new Error(`Failed to load: ${resp.status}`);
  return resp.json();
}
