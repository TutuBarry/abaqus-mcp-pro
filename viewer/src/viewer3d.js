/**
 * Viewer3D — Three.js scene management for FEM results.
 * Handles mesh generation, camera, animation, and rendering.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
import { sampleColormap } from './colormaps.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { parseVTU } from './vtuparser.js';

// ── Element type face definitions (Abaqus node ordering) ──
const SOLID_FACES = {
  4:  [[0,1,2],[0,2,3],[0,3,1],[1,3,2]],                           // C3D4
  5:  [[0,3,2,1],[0,1,4],[1,2,4],[2,3,4],[3,0,4]],                 // C3D5
  6:  [[0,2,1],[3,4,5],[0,1,4,3],[1,2,5,4],[2,0,3,5]],             // C3D6
  8:  [[0,1,2,3],[4,7,6,5],[0,4,5,1],[1,5,6,2],[2,6,7,3],[3,7,4,0]], // C3D8
};

const SHELL_FACES = {
  3: [[0,1,2]],       // S3 / M3D3
  4: [[0,1,2,3]],     // S4 / M3D4
};

export class Viewer3D {
  constructor(containerId) {
    this.containerId = containerId;
    this.container = null;
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.gridHelper = null;
    this.meshGroup = new THREE.Group();
    this.wireframeGroup = new THREE.Group();
    this.clipGroup = new THREE.Group(); // for clipping plane visualization
    this.clipPlane = null;
    this.animFrameId = null;
    this._disposed = false;
    this._fileCache = null;  // Map<filename, text> for uploaded VTU files
    this.labelRenderer = null;
    this.axisScene = null;
    this.axisCamera = null;
    this.axisGroup = null;
    this.probeResult = null;
    this._onPickCallback = null;
    this._onLoadStart = null;
    this._onLoadEnd = null;
  }

  init() {
    this.container = document.getElementById(this.containerId);
    if (!this.container) throw new Error(`Container #${this.containerId} not found`);

    const rect = this.container.getBoundingClientRect();
    const w = rect.width || 800;
    const h = rect.height || 600;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0d1117); // GitHub dark

    this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 10000);
    this.camera.position.set(1.2, 0.8, 1.5);

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
    });
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = false;
    this.renderer.localClippingEnabled = true;
    this.container.appendChild(this.renderer.domElement);

    // CSS2D label renderer for axis labels, probe tooltips
    this.labelRenderer = new CSS2DRenderer();
    this.labelRenderer.setSize(w, h);
    this.labelRenderer.domElement.style.position = 'absolute';
    this.labelRenderer.domElement.style.top = '0';
    this.labelRenderer.domElement.style.left = '0';
    this.labelRenderer.domElement.style.pointerEvents = 'none';
    this.container.appendChild(this.labelRenderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 0.1;
    this.controls.maxDistance = 5000;

    // Grid
    this.gridHelper = new THREE.GridHelper(5, 20, 0x444466, 0x333355);
    this.scene.add(this.gridHelper);

    // Lighting (PBR-optimized)
    const ambient = new THREE.AmbientLight(0x404060, 0.6);
    this.scene.add(ambient);

    const hemi = new THREE.HemisphereLight(0x87ceeb, 0x362d59, 0.8);
    this.scene.add(hemi);

    const d1 = new THREE.DirectionalLight(0xffeedd, 2.0);
    d1.position.set(2, 3, 1.5);
    this.scene.add(d1);

    const d2 = new THREE.DirectionalLight(0xbbddff, 0.8);
    d2.position.set(-1.5, 0.5, -2);
    this.scene.add(d2);

    const d3 = new THREE.DirectionalLight(0xffffff, 0.4);
    d3.position.set(-0.5, -1, 0.5);
    this.scene.add(d3);

    // Tone mapping for cinematic look
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.2;
    // Environment map for PBR reflections
    this._generateEnvMap();

    this.scene.add(this.meshGroup);
    this.scene.add(this.wireframeGroup);

    // Resize handler
    window.addEventListener('resize', () => this._onResize());

    // Start loop
    this._animate();
    this._buildAxisIndicator();
  }

  /* ── Drop Zone Overlay ── */
  _showDropOverlay(show) {
    const el = document.getElementById("drop-zone");
    if (el) el.classList.toggle("hidden", !show);
  }

  /* ── Environment Map Generation ── */
  _generateEnvMap() {
    try {
      const pmremGenerator = new THREE.PMREMGenerator(this.renderer);
      pmremGenerator.compileEquirectangularShader();
      const envScene = new RoomEnvironment();
      const envMap = pmremGenerator.fromScene(envScene, 0.04).texture;
      this.scene.environment = envMap;
      pmremGenerator.dispose();
    } catch (e) {
      console.warn('Env map failed, using default lighting:', e);
    }
  }

  /* ── Axis Indicator (top-right corner) ── */
  _buildAxisIndicator() {
    this.axisScene = new THREE.Scene();
    this.axisCamera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
    this.axisCamera.position.set(3, 2, 4);
    this.axisCamera.lookAt(0, 0, 0);

    const len = 1.0;
    const colors = [0xff4444, 0x44ff44, 0x4488ff];
    const labels = ['X', 'Y', 'Z'];
    const dirs = [[1,0,0], [0,1,0], [0,0,1]];
    const g = new THREE.Group();

    for (let i = 0; i < 3; i++) {
      // Line
      const pts = [new THREE.Vector3(0,0,0), new THREE.Vector3(dirs[i][0]*len, dirs[i][1]*len, dirs[i][2]*len)];
      const geom = new THREE.BufferGeometry().setFromPoints(pts);
      const mat = new THREE.LineBasicMaterial({ color: colors[i] });
      g.add(new THREE.Line(geom, mat));

      // Arrow cone
      const cone = new THREE.Mesh(
        new THREE.ConeGeometry(0.06, 0.15, 8),
        new THREE.MeshBasicMaterial({ color: colors[i] })
      );
      cone.position.set(dirs[i][0]*len, dirs[i][1]*len, dirs[i][2]*len);
      if (i === 0) cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), new THREE.Vector3(1,0,0));
      else if (i === 2) cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), new THREE.Vector3(0,0,1));
      g.add(cone);

      // CSS2D label
      const div = document.createElement('div');
      div.textContent = labels[i];
      div.style.color = ['#ff6666', '#66ff66', '#6699ff'][i];
      div.style.fontSize = '12px';
      div.style.fontWeight = 'bold';
      div.style.fontFamily = 'monospace';
      div.style.textShadow = '0 0 4px rgba(0,0,0,0.8)';
      const label = new CSS2DObject(div);
      label.position.set(dirs[i][0]*(len+0.2), dirs[i][1]*(len+0.2), dirs[i][2]*(len+0.2));
      g.add(label);
    }

    this.axisGroup = g;
    this.axisScene.add(g);
  }

  /* ── Click-to-pick / Probe ── */
  /**
   * Raycast to find closest mesh intersection
   */
  pick(screenX, screenY) {
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(new THREE.Vector2(screenX, screenY), this.camera);
    const meshes = [];
    this.meshGroup.children.forEach(c => { if (c.isMesh) meshes.push(c); });
    this.wireframeGroup.children.forEach(c => { if (c.isMesh) meshes.push(c); });
    const hits = raycaster.intersectObjects(meshes, true);
    return hits.length > 0 ? hits[0] : null;
  }

  /**
   * Register callback for pick events
   */
  onPick(callback) {
    this._onPickCallback = callback;
  }

  /**
   * Get field value at the nearest vertex to a point
   */
  getFieldValueAtPoint(point) {
    const r = this._lastVtuResult;
    if (!r) return null;
    const posArr = r.positions;
    const fieldVals = r.fieldValues;
    if (!fieldVals) return null;
    const n = posArr.length / 3;
    let best = 0, minD = Infinity;
    for (let i = 0; i < n; i++) {
      const dx = posArr[i*3] - point.x, dy = posArr[i*3+1] - point.y, dz = posArr[i*3+2] - point.z;
      const d = dx*dx + dy*dy + dz*dz;
      if (d < minD) { minD = d; best = i; }
    }
    return { value: fieldVals[best], index: best, position: [posArr[best*3], posArr[best*3+1], posArr[best*3+2]] };
  }

  getFieldRange() {
    const r = this._lastVtuResult;
    if (!r || !r.fieldValues) return { min: 0, max: 1 };
    const v = r.fieldValues;
    let mn = Infinity, mx = -Infinity;
    for (const x of v) { if (x != null && isFinite(x)) { if (x < mn) mn = x; if (x > mx) mx = x; } }
    return mn === Infinity ? { min: 0, max: 1 } : { min: mn, max: mx };
  }

  dispose() {
    this._disposed = true;
    if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
    if (this.renderer) {
      this.renderer.dispose();
      if (this.renderer.domElement.parentNode) {
        this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
      }
    }
  }

  // ── Scene building ──

  /**
   * Build/rebuild the 3D scene from model data.
   * @param {object} data - v1.0 JSON model data
   * @param {object} options
   * @param {number} options.frameIdx - frame index
   * @param {object} options.field - field descriptor {name, key, ...}
   * @param {boolean} options.deformed - apply displacement
   * @param {number} options.scaleFactor - deformation scale
   * @param {string} options.colormap - colormap name
   */
  buildScene(data, options = {}) {
    const {
      frameIdx = 0,
      field = null,
      deformed = false,
      scaleFactor = 1.0,
      colormap = 'jet',
    } = options;

    this.meshGroup.clear();
    this.wireframeGroup.clear();

    const nodes = data.nodes || [];
    const elements = data.elements || {};
    const frames = data.frames || [];

    if (nodes.length === 0) {
      this._showDropOverlay(true);
      return;
    }
    this._showDropOverlay(false);

    const frameData = frames[frameIdx] || frames[0] || {};
    let disp = null;
    if (deformed && frameData) {
      disp = frameData.displacement || frameData.U || null;
    }

    // Extract field values
    let fieldVals = null, fieldMin = 0, fieldMax = 1;
    if (field && frameData) {
      const fdata = frameData[field.key || field.name];
      if (fdata) {
        fieldVals = fdata.values || fdata;
        fieldMin = fdata.min !== undefined ? fdata.min : (fieldVals ? Math.min(...fieldVals.filter(v => v !== null && v !== undefined)) : 0);
        fieldMax = fdata.max !== undefined ? fdata.max : (fieldVals ? Math.max(...fieldVals.filter(v => v !== null && v !== undefined)) : 1);
      }
    }

    const allBounds = new THREE.Box3();
    let hasGeom = false;

    for (const [etype, conn] of Object.entries(elements)) {
      if (!conn || conn.length === 0) continue;
      if (!conn[0] || conn[0].length < 3) continue;
      const npe = conn[0].length;
      const result = this._buildGeom(
        nodes, conn, etype, npe,
        disp, scaleFactor,
        fieldVals, fieldMin, fieldMax, colormap
      );
      if (!result || result.positions.length === 0) continue;

      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.Float32BufferAttribute(result.positions, 3));
      geom.setIndex(result.indices);
      if (result.colors && result.colors.length > 0) {
        geom.setAttribute('color', new THREE.Float32BufferAttribute(result.colors, 3));
      }
      geom.computeVertexNormals();

      const hasColors = !!(result.colors && result.colors.length > 0);
      const mat = new THREE.MeshStandardMaterial({
        vertexColors: hasColors,
        color: hasColors ? 0xffffff : 0x58a6ff,
        metalness: 0.05,
        roughness: 0.45,
        side: THREE.DoubleSide,
        transparent: false,
        envMapIntensity: 0.5,
      });
      const mesh = new THREE.Mesh(geom, mat);
      this.meshGroup.add(mesh);

      // Wireframe
      const wGeom = geom.clone();
      const wf = new THREE.Mesh(wGeom, new THREE.MeshBasicMaterial({
        color: 0x8b949e,
        wireframe: true,
        transparent: true,
        opacity: 0.35,
      }));
      wf.visible = false;
      this.wireframeGroup.add(wf);

      if (result.bounds) {
        allBounds.expandByPoint(result.bounds.min);
        allBounds.expandByPoint(result.bounds.max);
      }
      hasGeom = true;
    }

    if (!hasGeom) return;
    this._fitCamera(allBounds);

    // Return metadata for UI
    return { bounds: allBounds };
  }


 // ── VTU-based scene building ──
  /**
   * Build geometry from node/element data.
   * Converts hex/tet/wedge elements to triangle meshes with optional deformation and field coloring.
   */
  _buildGeom(nodes, conn, etype, npe, disp, scaleFactor, fieldVals, fieldMin, fieldMax, colormap) {
    const positions = [];
    const indices = [];
    const colors = [];
    const minPt = [Infinity, Infinity, Infinity];
    const maxPt = [-Infinity, -Infinity, -Infinity];
    let idx = 0;
    const hasDisp = !!(disp && disp.length >= nodes.length);

    // Face definitions per element type (indices into element connectivity)
    const FACE_DEFS = {
      8: [ // C3D8 hexahedron: 6 quad faces
        [0,1,2,3], [4,7,6,5], [0,4,5,1],
        [1,5,6,2], [2,6,7,3], [3,7,4,0]
      ],
      4: [ // C3D4 tetrahedron: 4 triangle faces
        [0,1,3], [1,2,3], [2,0,3], [0,2,1]
      ],
      6: [ // C3D6 wedge: 3 quad + 2 triangle faces
        [0,1,4,3], [1,2,5,4], [2,0,3,5], [0,2,1], [3,4,5]
      ],
    };

    const faces = FACE_DEFS[npe] || FACE_DEFS[8];

    for (let ei = 0; ei < conn.length; ei++) {
      const elem = conn[ei];
      for (const face of faces) {
        // Get vertices for this face
        const vi = [face[0], face[1], face[2]];
        if (face.length === 4) vi.push(face[3]);

        // Triangle 1: (v0, v1, v2)
        for (let t = 0; t < 2; t++) {
          const a = t === 0 ? vi[0] : vi[0];
          const b = t === 0 ? vi[1] : vi[2];
          const c = t === 0 ? vi[2] : vi[3];
          if (c === undefined) break;

          for (const v of [a, b, c]) {
            const nodeIdx = elem[v] - 1;  // Abaqus 1-based to 0-based
            if (nodeIdx < 0 || nodeIdx >= nodes.length) continue;
            const nx = nodes[nodeIdx][0];
            const ny = nodes[nodeIdx][1];
            const nz = nodes[nodeIdx][2];

            let px = nx, py = ny, pz = nz;
            if (hasDisp) {
              px += disp[nodeIdx][0] * scaleFactor;
              py += disp[nodeIdx][1] * scaleFactor;
              pz += disp[nodeIdx][2] * scaleFactor;
            }
            positions.push(px, py, pz);

            if (px < minPt[0]) minPt[0] = px;
            if (py < minPt[1]) minPt[1] = py;
            if (pz < minPt[2]) minPt[2] = pz;
            if (px > maxPt[0]) maxPt[0] = px;
            if (py > maxPt[1]) maxPt[1] = py;
            if (pz > maxPt[2]) maxPt[2] = pz;

            indices.push(idx++);

            if (fieldVals) {
              const fv = fieldVals[nodeIdx] != null ? fieldVals[nodeIdx] : 0;
              const tVal = fieldMax > fieldMin ? (fv - fieldMin) / (fieldMax - fieldMin) : 0.5;
              const rgb = this._colormapValue(colormap || 'jet', Math.max(0, Math.min(1, tVal)));
              colors.push(rgb[0], rgb[1], rgb[2]);
            }
          }
        }
      }
    }

    return {
      positions,
      indices,
      colors: colors.length > 0 ? colors : null,
      bounds: {
        min: new THREE.Vector3(minPt[0], minPt[1], minPt[2]),
        max: new THREE.Vector3(maxPt[0], maxPt[1], maxPt[2]),
      },
    };
  }

  /**
   * Evaluate colormap at normalized position t in [0,1].
   * Returns [r, g, b] in 0-1 range.
   */
  _colormapValue(name, t) {
    // Use the imported sampleColormap function directly
    try {
      return sampleColormap(name, t);
    } catch (_) {}
    // Fallback: simple gradient
    const r = t < 0.5 ? 0 : (t - 0.5) * 2;
    const g = t < 0.5 ? t * 2 : 2 - t * 2;
    const b = t < 0.5 ? 1 - t * 2 : 0;
    return [r, g, b];
  }

  async buildSceneFromVTU(vtuUrlOrData, options = {}) {
    const { field = null, frameIdx = 0, colormap = 'jet', deformed = false, scaleFactor = 1.0 } = options;
    this.meshGroup.clear();
    this.wireframeGroup.clear();
    // Line group for beams/trusses
    this._lineGroup = this._lineGroup || new THREE.Group();
    if (this._lineGroup.parent) this._lineGroup.parent.remove(this._lineGroup);
    this._lineGroup = new THREE.Group();

    // ── Handle model.json metadata (format_version + frames) ──
    if (
      typeof vtuUrlOrData === 'object' &&
      vtuUrlOrData !== null &&
      vtuUrlOrData.format_version &&
      Array.isArray(vtuUrlOrData.frames)
    ) {
      const frames = vtuUrlOrData.frames;
      const frameEntry = frames[frameIdx] || frames[0];
      if (!frameEntry || !frameEntry.vtu_file) {
        console.error('VTU: no frame file for index', frameIdx, 'frames:', frames.length);
        this._showDropOverlay(true);
        return;
      }

      // Resolve VTU file path
      let vtuUrl = frameEntry.vtu_file;
      // If vtu_file is relative, resolve against _baseUrl or server root
      if (!vtuUrl.startsWith('/') && !vtuUrl.startsWith('http') && !vtuUrl.startsWith('file:')) {
        if (vtuUrlOrData._baseUrl) {
          const base = vtuUrlOrData._baseUrl;
          const lastSlash = base.lastIndexOf('/');
          const baseDir = lastSlash >= 0 ? base.substring(0, lastSlash + 1) : '';
          vtuUrl = baseDir + vtuUrl;
        } else {
          vtuUrl = '/' + vtuUrl;
        }
      }

      // Resolve VTU filename for cache lookup
      const vtuFilename = frameEntry.vtu_file.split('/').pop().split('\\').pop();

      // Check file cache (uploaded VTU files)
      let text = null;
      if (this._fileCache && this._fileCache.has(vtuFilename)) {
        text = this._fileCache.get(vtuFilename);
      } else {
        try {
          const resp = await fetch(vtuUrl);
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          text = await resp.text();
        } catch (e) {
          console.error('VTU fetch/parse failed:', vtuUrl, e);
          if (typeof vtuUrlOrData === 'object' && vtuUrlOrData._baseUrl) {
            console.warn('Uploaded model.json: VTU files not found in upload or on server.');
          }
          this._showDropOverlay(true);
          return;
        }
      }

      try {
        const fieldName = field ? (field.key || field.name) : undefined;
        const parsed = parseVTU(text, fieldName ? { fieldName } : {});
        parsed._metadata = vtuUrlOrData;
        vtuUrlOrData = parsed;
      } catch (e) {
        console.error('VTU parse failed:', e);
        this._showDropOverlay(true);
        return;
      }
    }

    let vtuResult;
    if (typeof vtuUrlOrData === 'string') {
      try {
        const resp = await fetch(vtuUrlOrData);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const text = await resp.text();
        vtuResult = parseVTU(text);
      } catch (e) {
        console.error('VTU fetch failed:', vtuUrlOrData, e);
        this._showDropOverlay(true);
        return;
      }
    } else {
      vtuResult = vtuUrlOrData;
    }
    if (!vtuResult || vtuResult.positions.length === 0) { this._showDropOverlay(true); return; }
    this._showDropOverlay(false);
    this._lastVtuResult = vtuResult;

  // -- Deformation toggle for VTU v3.0 (with U 3-component vector) --
  if (vtuResult._metadata && vtuResult._metadata.deformation_scale_factor !== undefined &&
      vtuResult.vectorFields && vtuResult.vectorFields["U"]) {
    const exportScale = vtuResult._metadata.deformation_scale_factor;
    const uData = vtuResult.vectorFields["U"].values;
    const nNodes = vtuResult.positions.length / 3;

    // Compute undeformed: initial = positions - U * exportScale
    const undeformed = new Float32Array(vtuResult.positions.length);
    for (let i = 0; i < nNodes; i++) {
      const b = i * 3;
      undeformed[b]     = vtuResult.positions[b]     - uData[b]     * exportScale;
      undeformed[b + 1] = vtuResult.positions[b + 1] - uData[b + 1] * exportScale;
      undeformed[b + 2] = vtuResult.positions[b + 2] - uData[b + 2] * exportScale;
    }

    if (deformed && scaleFactor > 0) {
      // Render deformed: initial + U * scaleFactor
      const renderPos = new Float32Array(vtuResult.positions.length);
      for (let i = 0; i < nNodes; i++) {
        const b = i * 3;
        renderPos[b]     = undeformed[b]     + uData[b]     * scaleFactor;
        renderPos[b + 1] = undeformed[b + 1] + uData[b + 1] * scaleFactor;
        renderPos[b + 2] = undeformed[b + 2] + uData[b + 2] * scaleFactor;
      }
      vtuResult.positions = renderPos;
    } else {
      // Render undeformed
      vtuResult.positions = undeformed;
    }
  }
    const fieldVals = vtuResult.fieldValues;
    const fieldMin = vtuResult.fieldMin !== undefined ? vtuResult.fieldMin : 0;
    const fieldMax = vtuResult.fieldMax !== undefined ? vtuResult.fieldMax : 1;
    const allBounds = new THREE.Box3();
    const positions = vtuResult.positions;
    const indices = vtuResult.indices;
    const lines = vtuResult.lines || [];
    const nNodes = positions.length / 3;
    let hasGeom = false;
    const outPos = [];
    const outIndices = [];
    const outColors = [];
    let boundsMin = null, boundsMax = null;
    for (let i = 0; i < nNodes; i++) {
      const x = positions[i * 3];
      const y = positions[i * 3 + 1];
      const z = positions[i * 3 + 2];
      outPos.push(x, y, z);
      if (boundsMin === null) { boundsMin = [x, y, z]; boundsMax = [x, y, z]; }
      else {
        if (x < boundsMin[0]) boundsMin[0] = x;
        if (y < boundsMin[1]) boundsMin[1] = y;
        if (z < boundsMin[2]) boundsMin[2] = z;
        if (x > boundsMax[0]) boundsMax[0] = x;
        if (y > boundsMax[1]) boundsMax[1] = y;
        if (z > boundsMax[2]) boundsMax[2] = z;
      }
      if (fieldVals) {
        const v = (i < fieldVals.length && fieldVals[i] != null) ? fieldVals[i] : 0;
        const t = fieldMax > fieldMin ? (v - fieldMin) / (fieldMax - fieldMin) : 0.5;
        const col = sampleColormap(colormap, t);
        outColors.push(col[0], col[1], col[2]);
      }
    }
    // --- Mesh (surface/volume) ---
    if (indices.length > 0) {
      outIndices.push(...indices);
      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.Float32BufferAttribute(outPos, 3));
      geom.setIndex(outIndices);
      if (outColors.length > 0) geom.setAttribute('color', new THREE.Float32BufferAttribute(outColors, 3));
      geom.computeVertexNormals();
      const hasColors = outColors.length > 0;
      const mat = new THREE.MeshStandardMaterial({
        vertexColors: hasColors,
        color: hasColors ? 0xffffff : 0x58a6ff,
        metalness: 0.05,
        roughness: 0.45,
        side: THREE.DoubleSide,
        envMapIntensity: 0.5,
      });
      const mesh = new THREE.Mesh(geom, mat);
      this.meshGroup.add(mesh);
      const wGeom = geom.clone();
      const wf = new THREE.Mesh(wGeom, new THREE.MeshBasicMaterial({
        color: 0x8b949e,
        wireframe: true,
        transparent: true,
        opacity: 0.35,
      }));
      wf.visible = false;
      this.wireframeGroup.add(wf);
      hasGeom = true;
    }

    // --- Lines (beams/trusses) ---
    if (lines.length > 0) {
      const linePositions = [];
      const lineColors = [];
      for (let i = 0; i < lines.length; i += 2) {
        const i0 = lines[i];
        const i1 = lines[i + 1];
        const x0 = positions[i0 * 3], y0 = positions[i0 * 3 + 1], z0 = positions[i0 * 3 + 2];
        const x1 = positions[i1 * 3], y1 = positions[i1 * 3 + 1], z1 = positions[i1 * 3 + 2];
        linePositions.push(x0, y0, z0, x1, y1, z1);
        if (fieldVals) {
          const v0 = (i0 < fieldVals.length && fieldVals[i0] != null) ? fieldVals[i0] : 0;
          const v1 = (i1 < fieldVals.length && fieldVals[i1] != null) ? fieldVals[i1] : 0;
          const t0 = fieldMax > fieldMin ? (v0 - fieldMin) / (fieldMax - fieldMin) : 0.5;
          const t1 = fieldMax > fieldMin ? (v1 - fieldMin) / (fieldMax - fieldMin) : 0.5;
          const col0 = sampleColormap(colormap, t0);
          const col1 = sampleColormap(colormap, t1);
          lineColors.push(col0[0], col0[1], col0[2], col1[0], col1[1], col1[2]);
        }
      }
      const lineGeom = new THREE.BufferGeometry();
      lineGeom.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
      if (lineColors.length > 0) lineGeom.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3));
      const lineMat = new THREE.LineBasicMaterial({
        vertexColors: lineColors.length > 0,
        color: lineColors.length > 0 ? 0xffffff : 0x88ccff,
        linewidth: 1,
      });
      const lineSegments = new THREE.LineSegments(lineGeom, lineMat);
      this._lineGroup.add(lineSegments);
      this.scene.add(this._lineGroup);
      hasGeom = true;
    }

    if (!hasGeom) return;
    this._fitCamera(allBounds);
    return { bounds: allBounds };
  }  getVtuStats() {
    if (!this._lastVtuResult) return { nodes: 0, elements: 0 };
    return {
      nodes: Math.floor(this._lastVtuResult.positions.length / 3),
      elements: (this._lastVtuResult.indices || []).length / 3 >> 0,
    };
  }

  // ── Camera ──

  _fitCamera(box) {
    if (!box || box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    const s = size || 1;
    this.camera.position.copy(center.clone().add(new THREE.Vector3(s * 0.8, s * 0.6, s * 1.0)));
    this.controls.target.copy(center);
    this.controls.update();

    // Update grid
    if (this.gridHelper) {
      this.scene.remove(this.gridHelper);
      this.gridHelper.geometry.dispose();
      this.gridHelper.material.dispose();
    }
    const gridSize = Math.pow(10, Math.ceil(Math.log10(s * 0.7)));
    this.gridHelper = new THREE.GridHelper(gridSize, 20, 0x444466, 0x333355);
    this.scene.add(this.gridHelper);
  }

  resetCamera() {
    if (this.meshGroup.children.length === 0) return;
    const box = new THREE.Box3().setFromObject(this.meshGroup);
    this._fitCamera(box);
  }

  setView(direction) {
    if (this.meshGroup.children.length === 0) return;
    const box = new THREE.Box3().setFromObject(this.meshGroup);
    const center = box.isEmpty() ? new THREE.Vector3(0, 0, 0) : box.getCenter(new THREE.Vector3());
    const s = box.isEmpty() ? 1 : box.getSize(new THREE.Vector3()).length();
    const offset = { top: [0, 1, 0.01], front: [0, 0, 1], right: [1, 0, 0], bottom: [0, -1, 0.01] };
    const [dx, dy, dz] = offset[direction] || offset.front;
    this.camera.position.set(center.x + dx * s, center.y + dy * s, center.z + dz * s);
    this.controls.target.copy(center);
    this.controls.update();
  }

  // ── Clipping ──

  toggleClipping() {
    if (!this.clipPlane) {
      this.clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    }
    const enabled = !this._clippingEnabled;
    this._clippingEnabled = enabled;
    if (enabled) {
      this.meshGroup.children.forEach(c => {
        if (c.isMesh) c.material.clippingPlanes = [this.clipPlane];
      });
    } else {
      this.meshGroup.children.forEach(c => {
        if (c.isMesh) c.material.clippingPlanes = [];
      });
    }
    this.renderer.localClippingEnabled = true;
  }

  // ── Opacity ──

  setOpacity(opacity) {
    this.meshGroup.children.forEach(c => {
      if (c.isMesh) {
        c.material.transparent = opacity < 1;
        c.material.opacity = opacity;
        c.material.needsUpdate = true;
      }
    });
    this.wireframeGroup.children.forEach(c => {
      if (c.isMesh) {
        c.material.transparent = opacity < 1;
        c.material.opacity = opacity;
        c.material.needsUpdate = true;
      }
    });
  }

    // ── Playback ──

  setWireframe(visible) {
    this.wireframeGroup.children.forEach(c => { c.visible = visible; });
  }

  // ── Screenshot ──

  takeScreenshot(name) {
    this.renderer.render(this.scene, this.camera);
    const link = document.createElement('a');
    link.download = name || `abaqus-screenshot-${Date.now()}.png`;
    link.href = this.renderer.domElement.toDataURL('image/png');
    link.click();
  }


  // ── Internal ──

  _onResize() {
    if (!this.container || !this.camera || !this.renderer) return;
    const rect = this.container.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    if (this.labelRenderer) this.labelRenderer.setSize(w, h);
  }

  _animate() {
    if (this._disposed) return;
    this.animFrameId = requestAnimationFrame(() => this._animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);

    // Render axis indicator (top-right corner)
    if (this.axisGroup && this.axisCamera) {
      this.axisGroup.quaternion.copy(this.camera.quaternion);
      const vp = this.renderer.domElement.getBoundingClientRect();
      const sz = 110;
      const ox = vp.width - sz - 10;
      const oy = 8;
      const dpr = Math.min(window.devicePixelRatio, 2);
      this.renderer.setViewport(ox * dpr, (vp.height - oy - sz) * dpr, sz * dpr, sz * dpr);
      this.renderer.setScissor(ox * dpr, (vp.height - oy - sz) * dpr, sz * dpr, sz * dpr);
      this.renderer.setScissorTest(true);
      this.renderer.render(this.axisScene, this.axisCamera);
      this.renderer.setScissorTest(false);
      this.renderer.setViewport(0, 0, vp.width * dpr, vp.height * dpr);
    }

    // CSS2D labels
    if (this.labelRenderer) {
      this.labelRenderer.render(this.scene, this.camera);
    }
  }
}

