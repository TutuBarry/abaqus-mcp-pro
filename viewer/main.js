import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let scene, camera, renderer, controls, gridHelper;
let meshGroup = new THREE.Group();
let wireframeGroup = new THREE.Group();
let currentData = null, currentFrame = 0, currentField = null;
let deformedMode = false, wireframeVisible = false, scaleFactor = 1.0;
let playing = false, playTimer = null;
let exportedJsonPath = null;

const JET = [[0,0,0.56],[0,0,1],[0,0.5,1],[0,1,1],[0,1,0.5],[0.5,1,0],[1,1,0],[1,0.5,0],[1,0,0],[0.5,0,0]];

function jetColor(t) {
  t = Math.max(0, Math.min(1, t));
  const idx = t * (JET.length - 1), lo = Math.floor(idx), hi = Math.min(lo + 1, JET.length - 1), f = idx - lo;
  return [JET[lo][0]+(JET[hi][0]-JET[lo][0])*f, JET[lo][1]+(JET[hi][1]-JET[lo][1])*f, JET[lo][2]+(JET[hi][2]-JET[lo][2])*f];
}

// ── Element type face definitions (Abaqus node ordering) ──
// Each entry: [linearNodeCount, [[faceIndices], ...]]
// For quadratic elements, only the first linearNodeCount corner nodes are used.
const SOLID_FACES = {
  4:  [[0,1,2],[0,2,3],[0,3,1],[1,3,2]],                           // C3D4
  5:  [[0,3,2,1],[0,1,4],[1,2,4],[2,3,4],[3,0,4]],                 // C3D5 pyramid
  6:  [[0,2,1],[3,4,5],[0,1,4,3],[1,2,5,4],[2,0,3,5]],              // C3D6 wedge
  8:  [[0,1,2,3],[4,7,6,5],[0,4,5,1],[1,5,6,2],[2,6,7,3],[3,7,4,0]], // C3D8 hex
};

const SHELL_FACES = {
  3: [[0,1,2]],       // S3 / M3D3
  4: [[0,1,2,3]],     // S4 / M3D4
};

function isShellType(etype) {
  const s = etype.toUpperCase();
  return s.startsWith('S') || s.startsWith('M3D') || s.startsWith('SFM') || s.startsWith('STRI');
}

function getLinearNodeCount(etype, npe) {
  if (isShellType(etype)) {
    if (npe <= 3) return 3;
    if (npe <= 6) return 3;   // S6 quadratic tri → 3 corner nodes
    return 4;                  // S8 quadratic quad → 4 corner nodes
  }
  // Solid elements
  if (npe <= 4) return 4;     // C3D4
  if (npe <= 5) return 5;     // C3D5 pyramid
  if (npe <= 6) return 6;     // C3D6 wedge
  if (npe <= 8) return 8;     // C3D8 hex
  if (npe <= 10) return 4;    // C3D10 quadratic tet
  if (npe <= 15) return 6;    // C3D15 quadratic wedge
  if (npe <= 20) return 8;    // C3D20 quadratic hex
  return npe;
}

function getFaces(etype, npe) {
  const ln = getLinearNodeCount(etype, npe);
  if (isShellType(etype)) return SHELL_FACES[ln] || null;
  return SOLID_FACES[ln] || null;
}

function triangulateFace(face, localIdx, indices) {
  if (face.length === 3) {
    indices.push(localIdx[face[0]], localIdx[face[1]], localIdx[face[2]]);
  } else if (face.length === 4) {
    indices.push(localIdx[face[0]], localIdx[face[1]], localIdx[face[2]]);
    indices.push(localIdx[face[0]], localIdx[face[2]], localIdx[face[3]]);
  }
}

// ── Scene init ──
function initScene() {
  const c = document.getElementById('viewport');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a1a2e);
  camera = new THREE.PerspectiveCamera(45, c.clientWidth / c.clientHeight, 0.1, 10000);
  camera.position.set(1, 0.8, 1.5);
  gridHelper = new THREE.GridHelper(5, 20, 0x333355, 0x222244);
  scene.add(gridHelper);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(c.clientWidth, c.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  c.appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  scene.add(new THREE.AmbientLight(0x404060, 2.5));
  const d1 = new THREE.DirectionalLight(0xffffff, 1.5);
  d1.position.set(1, 1, 1);
  scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.8);
  d2.position.set(-0.5, -0.3, -0.8);
  scene.add(d2);
  scene.add(meshGroup);
  scene.add(wireframeGroup);
  window.addEventListener('resize', () => {
    camera.aspect = c.clientWidth / c.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(c.clientWidth, c.clientHeight);
  });
  c.addEventListener('dragover', e => e.preventDefault());
  c.addEventListener('drop', e => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) loadFile(f);
  });
}

async function loadFile(file) {
  try {
    currentData = JSON.parse(await file.text());
    currentFrame = 0;
    buildScene(currentData);
  } catch (e) {
    console.error('Load failed:', e);
    alert('Parse error: ' + e.message);
  }
}

// ── Build / rebuild scene ──
function buildScene(data) {
  meshGroup.clear();
  wireframeGroup.clear();
  const nodes = data.nodes || [];
  const elements = data.elements || {};
  const frames = data.frames || [];
  if (nodes.length === 0) {
    document.getElementById('drop-zone').classList.remove('hidden');
    return;
  }
  document.getElementById('drop-zone').classList.add('hidden');
  if (data.deformation_scale_factor) scaleFactor = data.deformation_scale_factor;
  const fields = data.fields || [];
  currentField = fields.length > 0 ? fields[0] : null;
  let allBounds = new THREE.Box3();
  for (const etype of Object.keys(elements)) {
    const conn = elements[etype];
    if (!conn || conn.length === 0) continue;
    if (!conn[0] || conn[0].length < 3) continue;
    const npe = conn[0].length;
    const r = buildGeom(nodes, conn, etype, npe, frames, currentFrame, currentField);
    if (r.positions.length === 0) continue;
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(r.positions, 3));
    geom.setIndex(r.indices);
    if (r.colors && r.colors.length > 0) geom.setAttribute('color', new THREE.Float32BufferAttribute(r.colors, 3));
    geom.computeVertexNormals();
    const hasColors = !!(r.colors && r.colors.length > 0);
    const mat = new THREE.MeshPhongMaterial({
      vertexColors: hasColors,
      color: hasColors ? 0xffffff : 0x4488cc,
      specular: 0x111111, shininess: 30, side: THREE.DoubleSide
    });
    meshGroup.add(new THREE.Mesh(geom, mat));
    const wGeo = new THREE.BufferGeometry();
    wGeo.setAttribute('position', new THREE.Float32BufferAttribute(r.positions, 3));
    wGeo.setIndex(r.indices);
    const wf = new THREE.Mesh(wGeo, new THREE.MeshBasicMaterial({
      color: 0xcccccc, wireframe: true, transparent: true, opacity: 0.3
    }));
    wf.visible = false;
    wireframeGroup.add(wf);
    if (r.bounds) allBounds.expandByPoint(r.bounds.min).expandByPoint(r.bounds.max);
  }
  fitCamera();
  updateInfo(data);
  updateTree(data);
  updateLegend();
  updateAnimBar(data);
}

function buildGeom(nodes, conn, etype, npe, frames, frameIdx, field) {
  const positions = [], indices = [], colors = [];
  let boundsMin = null, boundsMax = null;
  let disp = null;
  if (deformedMode && frames.length > frameIdx) {
    disp = frames[frameIdx].displacement || frames[frameIdx].U || null;
  }
  const faces = getFaces(etype, npe);
  const linearN = getLinearNodeCount(etype, npe);
  let fieldVals = null, fieldMin = 0, fieldMax = 1;
  if (field && frames.length > frameIdx) {
    const fdata = frames[frameIdx][field.name] || frames[frameIdx][field.key] || null;
    if (fdata) {
      fieldVals = fdata.values || fdata;
      fieldMin = fdata.min !== undefined ? fdata.min : Math.min(...fieldVals);
      fieldMax = fdata.max !== undefined ? fdata.max : Math.max(...fieldVals);
    }
  }
  const nodeMap = {};
  for (const elem of conn) {
    const localIdx = [];
    // Use only corner nodes for quadratic elements
    const cornerNodes = elem.slice(0, linearN);
    for (const nid of cornerNodes) {
      if (nodeMap[nid] === undefined) {
        nodeMap[nid] = positions.length / 3;
        let x = nodes[nid][0] || 0, y = nodes[nid][1] || 0, z = nodes[nid][2] || 0;
        if (disp && disp[nid]) {
          x += disp[nid][0] * scaleFactor;
          y += disp[nid][1] * scaleFactor;
          z += disp[nid][2] * scaleFactor;
        }
        positions.push(x, y, z);
        // Track bounds
        if (boundsMin === null) {
          boundsMin = [x, y, z]; boundsMax = [x, y, z];
        } else {
          if (x < boundsMin[0]) boundsMin[0] = x;
          if (y < boundsMin[1]) boundsMin[1] = y;
          if (z < boundsMin[2]) boundsMin[2] = z;
          if (x > boundsMax[0]) boundsMax[0] = x;
          if (y > boundsMax[1]) boundsMax[1] = y;
          if (z > boundsMax[2]) boundsMax[2] = z;
        }
        if (fieldVals) {
          const v = fieldVals[nid] !== undefined ? fieldVals[nid] : 0;
          const t = fieldMax > fieldMin ? (v - fieldMin) / (fieldMax - fieldMin) : 0.5;
          const c = jetColor(t);
          colors.push(c[0], c[1], c[2]);
        }
      }
      localIdx.push(nodeMap[nid]);
    }
    if (faces) {
      for (const f of faces) triangulateFace(f, localIdx, indices);
    } else {
      // Fan triangulation fallback for unknown element types
      for (let i = 1; i < linearN - 1; i++) {
        indices.push(localIdx[0], localIdx[i], localIdx[i + 1]);
      }
    }
  }
  const r = { positions, indices, colors };
  if (boundsMin) {
    r.bounds = {
      min: new THREE.Vector3(boundsMin[0], boundsMin[1], boundsMin[2]),
      max: new THREE.Vector3(boundsMax[0], boundsMax[1], boundsMax[2])
    };
  }
  return r;
}

function fitCamera() {
  if (meshGroup.children.length === 0) return;
  const box = new THREE.Box3().setFromObject(meshGroup);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  const s = size || 1;
  camera.position.copy(center.clone().add(new THREE.Vector3(s * 0.8, s * 0.6, s * 1.0)));
  controls.target.copy(center);
  controls.update();
  // Scale grid to match model size
  if (gridHelper) {
    scene.remove(gridHelper);
    gridHelper.geometry.dispose();
    gridHelper.material.dispose();
  }
  const gridSize = Math.pow(10, Math.ceil(Math.log10(s * 0.7)));
  gridHelper = new THREE.GridHelper(gridSize, 20, 0x333355, 0x222244);
  scene.add(gridHelper);
}

// ── UI helpers ──
function updateInfo(data) {
  const nodes = data.nodes || [];
  const elems = data.elements || {};
  const frames = data.frames || [];
  let totalElems = 0;
  for (const etype of Object.keys(elems)) {
    totalElems += (elems[etype] || []).length;
  }
  // nodes is 1-indexed with a null placeholder at [0]
  document.getElementById('info-nodes').textContent = (nodes.length - 1).toLocaleString();
  document.getElementById('info-elems').textContent = totalElems.toLocaleString();
  document.getElementById('info-frames').textContent = frames.length.toLocaleString();
}

function updateTree(data) {
  const tree = document.getElementById('tree');
  tree.innerHTML = '';
  const addSection = (title) => {
    const el = document.createElement('div');
    el.className = 'tree-section';
    el.textContent = title;
    tree.appendChild(el);
  };
  const addItem = (icon, label, onClick) => {
    const el = document.createElement('div');
    el.className = 'tree-item';
    el.innerHTML = `<span class="icon">${icon}</span>${label}`;
    if (onClick) el.addEventListener('click', onClick);
    tree.appendChild(el);
    return el;
  };

  addSection('Model');
  const nodes = data.nodes || [];
  const elems = data.elements || {};
  let totalElems = 0;
  const etypes = Object.keys(elems);
  for (const et of etypes) totalElems += (elems[et] || []).length;
  addItem('🔷', `Nodes: ${(nodes.length - 1).toLocaleString()}`);
  addItem('🔶', `Elements: ${totalElems.toLocaleString()}`);
  for (const et of etypes) {
    addItem('  ', `${et}: ${(elems[et] || []).length.toLocaleString()}`);
  }

  const fields = data.fields || [];
  if (fields.length > 0) {
    addSection('Fields');
    for (const f of fields) {
      const item = addItem('📊', f.label || f.name || f.key || 'Unknown', () => {
        currentField = f;
        rebuildFrame();
        updateLegend();
      });
      if (currentField && (currentField.key || currentField.name) === (f.key || f.name)) {
        item.classList.add('active');
      }
    }
  }

  const steps = data.steps || [];
  if (steps.length > 0) {
    addSection('Steps');
    for (const s of steps) {
      addItem('📋', s.label || s.name || 'Step');
    }
  }

  addSection('Info');
  if (data.model_name) addItem('📄', `Model: ${data.model_name}`);
  if (data.job_name) addItem('⚙', `Job: ${data.job_name}`);
  if (data.deformation_scale_factor) addItem('📏', `Scale: ${data.deformation_scale_factor}x`);
  if (data.abaqus_version) addItem('🔧', `Abaqus: ${data.abaqus_version}`);
  if (data.export_time) addItem('🕐', `Exported: ${data.export_time}`);
}

function updateLegend() {
  const title = document.getElementById('legend-title');
  const gradient = document.getElementById('legend-gradient');
  const minLabel = document.getElementById('legend-min');
  const maxLabel = document.getElementById('legend-max');
  if (!currentField || !currentData || currentData.frames.length <= currentFrame) {
    title.textContent = 'No field selected';
    gradient.style.background = '#333';
    minLabel.textContent = '0';
    maxLabel.textContent = '0';
    return;
  }
  const frame = currentData.frames[currentFrame];
  const fdata = frame[currentField.name] || frame[currentField.key] || null;
  if (!fdata) {
    title.textContent = currentField.label || currentField.name || 'No data';
    gradient.style.background = '#333';
    minLabel.textContent = '0';
    maxLabel.textContent = '0';
    return;
  }
  const fmin = fdata.min !== undefined ? fdata.min : 0;
  const fmax = fdata.max !== undefined ? fdata.max : 1;
  const unit = currentField.unit || '';
  title.textContent = `${currentField.label || currentField.name || 'Field'}${unit ? ' (' + unit + ')' : ''}`;
  const stops = JET.map((c, i) => `${i / (JET.length - 1) * 100}% rgb(${Math.round(c[0]*255)},${Math.round(c[1]*255)},${Math.round(c[2]*255)})`).join(',');
  gradient.style.background = `linear-gradient(to right, ${stops})`;
  const fmt = (v) => {
    if (Math.abs(v) < 0.001 || Math.abs(v) > 1e6) return v.toExponential(2);
    return parseFloat(v.toPrecision(4)).toString();
  };
  minLabel.textContent = fmt(fmin);
  maxLabel.textContent = fmt(fmax);
}

function updateAnimBar(data) {
  const bar = document.getElementById('anim-bar');
  const frames = data.frames || [];
  if (frames.length <= 1) {
    bar.classList.add('hidden');
    return;
  }
  bar.classList.remove('hidden');
  const slider = document.getElementById('frame-slider');
  slider.max = frames.length - 1;
  slider.value = currentFrame;
  document.getElementById('frame-label').textContent = `${currentFrame + 1} / ${frames.length}`;
  const frame = frames[currentFrame];
  if (frame && frame.time !== undefined) {
    document.getElementById('frame-time').textContent = `t=${parseFloat(frame.time.toPrecision(4))}`;
  } else {
    document.getElementById('frame-time').textContent = '';
  }
}

function rebuildFrame() {
  if (!currentData) return;
  buildScene(currentData);
  updateLegend();
  updateAnimBar(currentData);
}

function setFrame(idx) {
  if (!currentData) return;
  const max = Math.max(0, (currentData.frames || []).length - 1);
  currentFrame = Math.max(0, Math.min(idx, max));
  rebuildFrame();
}

function togglePlay() {
  if (!currentData || (currentData.frames || []).length <= 1) return;
  playing = !playing;
  const btn = document.getElementById('btn-play');
  btn.textContent = playing ? '\u23F8' : '\u25B6';
  if (playing) {
    playTimer = setInterval(() => {
      const max = (currentData.frames || []).length - 1;
      currentFrame = currentFrame >= max ? 0 : currentFrame + 1;
      rebuildFrame();
    }, 200);
  } else {
    if (playTimer) { clearInterval(playTimer); playTimer = null; }
  }
}

function setupUI() {
  document.getElementById('btn-wireframe').addEventListener('click', () => {
    wireframeVisible = !wireframeVisible;
    document.getElementById('btn-wireframe').classList.toggle('active', wireframeVisible);
    wireframeGroup.children.forEach(c => { c.visible = wireframeVisible; });
  });
  document.getElementById('btn-deformed').addEventListener('click', () => {
    deformedMode = !deformedMode;
    document.getElementById('btn-deformed').classList.toggle('active', deformedMode);
    rebuildFrame();
  });
  document.getElementById('btn-reset').addEventListener('click', () => fitCamera());
  document.getElementById('btn-top').addEventListener('click', () => {
    const box = new THREE.Box3().setFromObject(meshGroup);
    const c = box.isEmpty() ? new THREE.Vector3(0,0,0) : box.getCenter(new THREE.Vector3());
    const s = box.isEmpty() ? 1 : box.getSize(new THREE.Vector3()).length();
    camera.position.set(c.x, c.y + s, c.z + 0.01);
    controls.target.copy(c);
    controls.update();
  });
  document.getElementById('btn-front').addEventListener('click', () => {
    const box = new THREE.Box3().setFromObject(meshGroup);
    const c = box.isEmpty() ? new THREE.Vector3(0,0,0) : box.getCenter(new THREE.Vector3());
    const s = box.isEmpty() ? 1 : box.getSize(new THREE.Vector3()).length();
    camera.position.set(c.x, c.y, c.z + s);
    controls.target.copy(c);
    controls.update();
  });
  document.getElementById('btn-right').addEventListener('click', () => {
    const box = new THREE.Box3().setFromObject(meshGroup);
    const c = box.isEmpty() ? new THREE.Vector3(0,0,0) : box.getCenter(new THREE.Vector3());
    const s = box.isEmpty() ? 1 : box.getSize(new THREE.Vector3()).length();
    camera.position.set(c.x + s, c.y, c.z);
    controls.target.copy(c);
    controls.update();
  });
  document.getElementById('btn-play').addEventListener('click', togglePlay);
  document.getElementById('btn-prev').addEventListener('click', () => setFrame(0));
  document.getElementById('btn-next').addEventListener('click', () => {
    if (currentData) setFrame((currentData.frames || []).length - 1);
  });
  const slider = document.getElementById('frame-slider');
  slider.addEventListener('input', () => setFrame(parseInt(slider.value)));
  document.getElementById('file-input').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (f) loadFile(f);
  });
  // ODB export
  document.getElementById('export-btn').addEventListener('click', exportFromOdb);
  document.getElementById('load-exported-btn').addEventListener('click', loadExportedJson);
  // Allow Enter key in ODB path input to trigger export
  document.getElementById('odb-path').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') exportFromOdb();
  });
  window.addEventListener('keydown', (e) => {
    switch (e.key.toLowerCase()) {
      case 'w': document.getElementById('btn-wireframe').click(); break;
      case 'd': document.getElementById('btn-deformed').click(); break;
      case 'r': document.getElementById('btn-reset').click(); break;
      case ' ': e.preventDefault(); togglePlay(); break;
      case 'arrowleft': setFrame(currentFrame - 1); break;
      case 'arrowright': setFrame(currentFrame + 1); break;
    }
  });
  const params = new URLSearchParams(window.location.search);
  const urlFile = params.get('file');
  if (urlFile) {
    fetch(urlFile).then(r => r.json()).then(data => {
      currentData = data;
      currentFrame = 0;
      buildScene(currentData);
    }).catch(err => console.error('URL load failed:', err));
  }
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

initScene();
setupUI();
animate();
// v1.1 - Full element type support (C3D4/5/6/8/10/15/20, S3/4/6/8, M3D3/4)
// Auto-scaling grid, bounds tracking, model-relative view buttons.
async function exportFromOdb() {
  const odbPath = document.getElementById('odb-path').value.trim();
  const statusEl = document.getElementById('export-status');
  const btn = document.getElementById('export-btn');
  const loadArea = document.getElementById('load-exported');

  if (!odbPath) {
    statusEl.textContent = 'Please enter an ODB path';
    statusEl.className = 'error';
    return;
  }

  btn.disabled = true;
  statusEl.textContent = 'Exporting from ODB... (this may take a while)';
  statusEl.className = '';
  loadArea.style.display = 'none';

  try {
    const resp = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ odb_path: odbPath, step_index: -1, frame_step: 1, deformation_scale: 1.0 })
    });
    const result = await resp.json();
    if (result.ok) {
      statusEl.textContent = 'Exported: ' + result.node_count.toLocaleString() + ' nodes, ' + result.elem_count.toLocaleString() + ' elements, ' + result.frame_count + ' frames';
      statusEl.className = 'success';
      exportedJsonPath = result.output_path;
      loadArea.style.display = 'block';
      // Auto-load the exported file
      const fname = exportedJsonPath.split(/[\\/]/).pop();
      const resp2 = await fetch('/' + fname);
      if (resp2.ok) {
        currentData = await resp2.json();
        currentFrame = 0;
        buildScene(currentData);
      }
    } else {
      statusEl.textContent = 'Export failed: ' + (result.error || 'Unknown error');
      statusEl.className = 'error';
    }
  } catch (err) {
    statusEl.textContent = 'Export error: ' + err.message;
    statusEl.className = 'error';
  } finally {
    btn.disabled = false;
  }
}

function loadExportedJson() {
  if (!exportedJsonPath) return;
  const fname = exportedJsonPath.split(/[\\/]/).pop();
  fetch('/' + fname).then(r => r.json()).then(data => {
    currentData = data;
    currentFrame = 0;
    buildScene(currentData);
  }).catch(err => console.error('Load exported failed:', err));
}

