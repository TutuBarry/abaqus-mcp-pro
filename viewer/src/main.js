/**
 * Abaqus MCP Pro - 3D Result Viewer
 * Entry point. Initializes the 3D viewer and UI.
 */
import './style.css';
import { Viewer3D } from './viewer3d.js';
import { UIController } from './ui.js';

function main() {
  const container = document.getElementById('viewport');
  if (!container) {
    console.error('Viewport element not found');
    return;
  }

  // Initialize 3D viewer
  const viewer = new Viewer3D(container);

  // Initialize UI controller
  const ui = new UIController(viewer);

  // Check for file URL parameter
  const params = new URLSearchParams(window.location.search);
  const urlFile = params.get('file');
  if (urlFile) {
    (async () => {
      try {
        const resp = await fetch(urlFile);
        if (resp.ok) {
          const data = await resp.json();
          await viewer.loadModel(data, location.href);
          ui._updateAll(data);
        }
      } catch (e) {
        console.error('URL file load failed:', e);
      }
    })();
  }

  // Expose for debugging
  window.__viewer = viewer;
  window.__ui = ui;
}

// Wait for DOM
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
