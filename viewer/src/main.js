import "./style.css";
import { Viewer3D } from "./viewer3d.js";
import { UIController } from "./ui.js";
import { ODBExportClient } from "./odbexport.js";

export const state = {
  data: null,
  format: "v1.0",
  currentFrame: 0,
  currentField: null,
  deformed: false,
  wireframe: false,
  clipping: false,
  playing: false,
  playTimer: null,
  colormapName: "jet",
  scaleFactor: 1.0,
  exportedJsonPath: null,
  loading: false,
};

const viewer = new Viewer3D("viewport");
const ui = new UIController(viewer, state);
const odb = new ODBExportClient(viewer, state, ui);

viewer.init();
ui.init();
odb.init();

document.getElementById("welcome-open-odb").addEventListener("click", () => {
  document.getElementById("welcome").classList.add("hidden");
  Object.keys(ui.panels).forEach(key => { ui.panels[key] = key === 'odb'; });
  ui._syncPanels();
  document.getElementById('odb-path').focus();
});

document.getElementById("welcome-open-file").addEventListener("click", () => {
  document.getElementById("welcome").classList.add("hidden");
  const fileInput = document.getElementById("file-input");
  if (fileInput) fileInput.click();
});

window.__viewer = { viewer, state, ui, odb };
console.log("ABAQUS MCP Pro Viewer 3.0 ready");

void odb.loadStartupResult();
