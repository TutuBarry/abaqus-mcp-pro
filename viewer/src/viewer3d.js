import {createContourMaterial, configureContour, contourCoordinates, featureEdges} from './contours.js';
import { FrameCache } from './framecache.js';
import { guardDragClicks, sampleControlInputs } from './gestures.js';
import { finiteRange } from "./vtuparser.js";
/**
 * Viewer3D — Three.js scene management for FEM results.
 * Handles mesh generation, camera, animation, and rendering.
 */

import * as THREE from 'three';
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js';
import { CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
import { sampleColormap } from './colormaps.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { parseVTU, selectVTUField, filterSurfaceIndices } from './vtuparser.js';

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
    this.edgeGroup = new THREE.Group();
    this._edgesVisible = true;
    this.contourBands = 12;
    this.clipGroup = new THREE.Group(); // for clipping plane visualization
    this.clipPlane = null;
    this.animFrameId = null;
    this._disposed = false;
    this._needsRender = true;
    this._axisPoint = new THREE.Vector3();
    this._fileCache = null;  // Map<filename, text> for uploaded VTU files
    this.labelRenderer = null;
    this.axisScene = null;
    this.axisCamera = null;
   this.axisGroup = null;
    this.axisRenderer = null;
   this.probeResult = null;
    this._onPickCallback = null;
    this._onLoadStart = null;
    this._onLoadEnd = null;
    this._clippingEnabled = false;
    this._clippingPosition = 0;
   this._animInterval = 200;
    this._axisDirs = [[1,0,0],[0,1,0],[0,0,1]];
    this._axisColors = ['#ff6666','#66ff66','#6699ff'];
    this._axisLabelElements = null;
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
      powerPreference: 'high-performance',
    });
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = false;
    this.renderer.localClippingEnabled = true;
    this.container.appendChild(this.renderer.domElement);
    // Prevent native canvas drag from interfering with camera manipulation.
    this.renderer.domElement.addEventListener('dragstart', (e) => e.preventDefault());
    this._removeDragClickGuard = guardDragClicks(this.renderer.domElement);

    // CSS2D label renderer for axis labels, probe tooltips
    this.labelRenderer = new CSS2DRenderer();
    this.labelRenderer.setSize(w, h);
    this.labelRenderer.domElement.style.position = 'absolute';
    this.labelRenderer.domElement.style.top = '0';
    this.labelRenderer.domElement.style.left = '0';
    this.labelRenderer.domElement.style.pointerEvents = 'none';
   this.container.appendChild(this.labelRenderer.domElement);

    // Separate transparent WebGL renderer for axis indicator (no black background)
    this.axisContainer = document.createElement('div');
    this.axisContainer.id = 'axis-indicator';
    this.axisContainer.style.cssText = 'position:absolute;top:80px;right:10px;width:170px;height:170px;z-index:20;pointer-events:none';
    this.container.appendChild(this.axisContainer);

    this.axisRenderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
    });
    this.axisRenderer.setSize(170, 170);
    this.axisRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.axisRenderer.setClearColor(0x000000, 0); // fully transparent background
    this.axisContainer.appendChild(this.axisRenderer.domElement);
    this.axisRenderer.domElement.style.display = 'block';

   this.controls = new TrackballControls(this.camera, this.renderer.domElement);
    this.controls.minDistance = 0.1;
    this.controls.maxDistance = 5000;
    this.controls.panSpeed = 0.8;
    this.controls.noRotate = false;
    this.controls.noZoom = false;
    this.controls.noPan = false;
    // Direct CAD-style manipulation: do not keep rotating after pointer release.
    this.controls.staticMoving = true;
    this.controls.rotateSpeed = 6.0;
    this.controls.zoomSpeed = 6.0;
    this._removeControlSampling = sampleControlInputs(this.renderer.domElement, this.controls);
    this.controls.addEventListener('change', () => this.requestRender());
    this.controls.addEventListener('start', () => this.controls.handleResize());

    // Grid
    this.gridHelper = new THREE.GridHelper(5, 20, 0x444466, 0x333355);
    this.gridHelper.visible = false;
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
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMappingExposure = 1.2;
    // Environment map for PBR reflections
    this._generateEnvMap();

    this.scene.add(this.meshGroup);
    this.scene.add(this.wireframeGroup);
    this.scene.add(this.edgeGroup);

    // Resize handler
    this._resizeHandler = () => this._onResize();
    window.addEventListener('resize', this._resizeHandler);
    this._resizeObserver = new ResizeObserver(this._resizeHandler);
    this._resizeObserver.observe(this.container);

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
    this.axisCamera.position.set(4, 2.5, 5);
    this.axisCamera.lookAt(0, 0, 0);

    const len = 1.6;
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
        new THREE.ConeGeometry(0.09, 0.22, 8),
        new THREE.MeshBasicMaterial({ color: colors[i] })
      );
      cone.position.set(dirs[i][0]*len, dirs[i][1]*len, dirs[i][2]*len);
      if (i === 0) cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), new THREE.Vector3(1,0,0));
      else if (i === 2) cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), new THREE.Vector3(0,0,1));
      g.add(cone);

    }

    this.axisGroup = g;
    this.axisScene.add(g);

    // Create HTML labels for X, Y, Z (positioned manually via 3D-to-screen projection)
    this._axisLabelElements = [];
    for (let i = 0; i < 3; i++) {
      const div = document.createElement('div');
      div.textContent = labels[i];
      div.style.cssText = 'position:absolute;color:' + this._axisColors[i] + ';font-size:18px;font-weight:bold;font-family:monospace;text-shadow:0 0 6px rgba(0,0,0,0.9);pointer-events:none;transform:translate(-50%,-50%)';
      this.axisContainer.appendChild(div);
      this._axisLabelElements.push(div);
    }
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
    this.controls?.dispose();
    this._removeDragClickGuard?.();
    this._removeControlSampling?.();
    this._resizeObserver?.disconnect();
    if (this._resizeHandler) window.removeEventListener('resize', this._resizeHandler);
   if (this.renderer) {
     this.renderer.dispose();
     if (this.renderer.domElement.parentNode) {
       this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
     }
   }
    if (this.axisRenderer) {
      this.axisRenderer.dispose();
      if (this._axisLabelElements) {
        this._axisLabelElements.forEach(el => {
          if (el.parentNode) el.parentNode.removeChild(el);
        });
        this._axisLabelElements = null;
      }
      if (this.axisContainer && this.axisContainer.parentNode) {
        this.axisContainer.parentNode.removeChild(this.axisContainer);
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
  _disposeGroup(group) {
    group.traverse(object => {
      object.geometry?.dispose();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of materials) material?.dispose();
    });
    group.clear();
  }

  clearResult() {
    this._loadVersion = (this._loadVersion || 0) + 1;
    for (const group of [this.meshGroup, this.wireframeGroup, this.edgeGroup, this._lineGroup]) {
      if (group) this._disposeGroup(group);
    }
    this._lastVtuResult = null;
    this._fileCache = null;
    this._parsedFrames?.clear();
    this._prefetchEpoch = (this._prefetchEpoch || 0) + 1;
    this.lastTimings = null;
    this.requestRender();
  }

  buildScene(data, options = {}) {
    this.requestRender();
    const {
      frameIdx = 0,
      field = null,
      deformed = false,
      scaleFactor = 1.0,
      colormap = 'jet',
      fieldMin: optFieldMin,
      fieldMax: optFieldMax,
      preserveCamera = false,  } = options;

    this._disposeGroup(this.meshGroup);
    this._disposeGroup(this.wireframeGroup);
    this._disposeGroup(this.edgeGroup);

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
        fieldMin = fdata.min !== undefined ? fdata.min : (fieldVals ? finiteRange(fieldVals).min : 0);
        fieldMax = fdata.max !== undefined ? fdata.max : (fieldVals ? finiteRange(fieldVals).max : 1);
      }
    }
    // Override with custom contour range if provided
    if (optFieldMin !== undefined) fieldMin = optFieldMin;
    if (optFieldMax !== undefined) fieldMax = optFieldMax;

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
    if (preserveCamera) {
      const pos = this.camera.position.clone();
      const target = this.controls.target.clone();
      this._fitCamera(allBounds);
      this.camera.position.copy(pos);
      this.controls.target.copy(target);
      this.controls.update();
    } else {
      this._fitCamera(allBounds);
    }

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
              const fv = fieldVals[nodeIdx] != null ? fieldVals[nodeIdx] : NaN;
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
    const loadVersion = this._loadVersion = (this._loadVersion || 0) + 1;
    const started = performance.now();
    const timings = {readMs: 0, parseMs: 0, acquireMs: 0, cacheHit: false, reusedGeometry: false};
    let prefetch = null;
    const { field = null, frameIdx = 0, colormap = 'jet', deformed = false, scaleFactor = 1.0, fieldMin: optFieldMin, fieldMax: optFieldMax, preserveCamera = false, } = options;

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
        throw new Error('指定结果帧不存在');
      }

      this._parsedFrames ||= new FrameCache();
      const metadata = vtuUrlOrData;
      const resolve = entry => {
        const name = entry.vtu_file;
        if (/^(https?:|file:|\/)/.test(name)) return name;
        const base = metadata._baseUrl || '/';
        return base.slice(0, base.lastIndexOf('/') + 1) + name;
      };
      const read = (entry, stats) => async signal => {
        const t0 = performance.now();
        const filename = entry.vtu_file.split(/[\\/]/).pop();
        let text = this._fileCache?.get(filename);
        if (text === undefined) {
          const response = await fetch(resolve(entry), {signal});
          if (!response.ok) throw new Error('HTTP ' + response.status);
          text = await response.text();
        }
        if (signal.aborted) throw new DOMException('Result changed', 'AbortError');
        const t1 = performance.now();
        const parsed = parseVTU(text, {retainCells:false});
        if (stats) { stats.readMs = t1 - t0; stats.parseMs = performance.now() - t1; }
        return parsed;
      };
      this._parsedFrames.cancelExcept(resolve(frameEntry));
      let cached;
      const acquireStarted = performance.now();
      try { cached = await this._parsedFrames.get(resolve(frameEntry), read(frameEntry, timings)); }
      catch (error) { if (loadVersion !== this._loadVersion) return; throw error; }
      timings.acquireMs = performance.now() - acquireStarted;
      if (loadVersion !== this._loadVersion) return;
      timings.cacheHit = cached.hit;
      const fieldName = field ? (field.component_index === -1 ? field.name : (field.key || field.name)) : undefined;
      vtuUrlOrData = selectVTUField(cached.value, fieldName, Math.max(0, field?.component_index || 0));
      vtuUrlOrData._metadata = metadata;
      const neighbor = frames[frameIdx + 1] || frames[frameIdx - 1];
      if (neighbor && (this._parsedFrames.entries.get(resolve(frameEntry))?.bytes || Infinity) <= this._parsedFrames.maxBytes / 2) {
        prefetch = () => this._parsedFrames.get(resolve(neighbor), read(neighbor)).catch(() => {});
      }

    }

    let vtuResult;
    if (typeof vtuUrlOrData === 'string') {
      try {
        const resp = await fetch(vtuUrlOrData);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const text = await resp.text();
        if (loadVersion !== this._loadVersion) return;
        vtuResult = parseVTU(text);
      } catch (e) {
        console.error('VTU fetch failed:', vtuUrlOrData, e);
        this._showDropOverlay(true);
        throw e;
      }
    } else {
      vtuResult = vtuUrlOrData;
    }
    if (!vtuResult || vtuResult.positions.length === 0) { this._showDropOverlay(true); throw new Error('VTU has no geometry'); }
    // Reuse GPU buffers when the displayed topology is unchanged.
    this._lineGroup ||= new THREE.Group();
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
    let fieldMin = vtuResult.fieldMin !== undefined ? vtuResult.fieldMin : 0;
    let fieldMax = vtuResult.fieldMax !== undefined ? vtuResult.fieldMax : 1;
    // Override with custom contour range if provided
    if (optFieldMin !== undefined) fieldMin = optFieldMin;
    if (optFieldMax !== undefined) fieldMax = optFieldMax;
    const allBounds = new THREE.Box3();
    const positions = vtuResult.positions;
    const bodyIds = vtuResult._metadata?.body_ids || [];
    const hidden = new Set(options.hiddenBodies || []);
    const indices = filterSurfaceIndices(vtuResult.indices, bodyIds, hidden,
      fieldVals, options.contactOnly && field?.association === 'contact');
    const lines = [];
    for (let i = 0; i < (vtuResult.lines || []).length; i += 2) {
      const a = vtuResult.lines[i], b = vtuResult.lines[i+1];
      if (!hidden.has(bodyIds[a]) && !hidden.has(bodyIds[b])) lines.push(a, b);
    }
    const nNodes = positions.length / 3;
    let hasGeom = false;
    const outPos = positions;
    const outColors = fieldVals && lines.length ? new Float32Array(nNodes * 3) : null;
    const lineColor = new THREE.Color();
    let boundsMin = null, boundsMax = null;
    for (let i = 0; i < nNodes; i++) {
      const x = positions[i * 3];
      const y = positions[i * 3 + 1];
      const z = positions[i * 3 + 2];

      if (boundsMin === null) { boundsMin = [x, y, z]; boundsMax = [x, y, z]; }
      else {
        if (x < boundsMin[0]) boundsMin[0] = x;
        if (y < boundsMin[1]) boundsMin[1] = y;
        if (z < boundsMin[2]) boundsMin[2] = z;
        if (x > boundsMax[0]) boundsMax[0] = x;
        if (y > boundsMax[1]) boundsMax[1] = y;
        if (z > boundsMax[2]) boundsMax[2] = z;
      }
      if (outColors) {
        const v = (i < fieldVals.length && fieldVals[i] != null) ? fieldVals[i] : NaN;
        const t = !Number.isFinite(v) ? NaN : fieldMax > fieldMin ? (v - fieldMin) / (fieldMax - fieldMin) : 0.5;
        const col = lineColor.setRGB(...sampleColormap(colormap, t), THREE.SRGBColorSpace);
        outColors.set([col.r,col.g,col.b], i * 3);
      }
    }
    const contour = contourCoordinates(fieldVals,nNodes,fieldMin,fieldMax);
    // --- Mesh (surface/volume) ---
    if (indices.length > 0) {
      const existing = this.meshGroup.children[0];
      const oldIndex = existing?.geometry.index?.array;
      const reusable = existing && existing.geometry.attributes.position.count === nNodes &&
        oldIndex?.length === indices.length && oldIndex.every((v, i) => v === indices[i]);
      const positionsChanged = !reusable || !existing.geometry.attributes.position.array.every((v,i)=>v===outPos[i]);
      const update = geom => {
        if (geom.attributes.position?.array.length === outPos.length) {
          geom.attributes.position.array.set(outPos);
          geom.attributes.position.needsUpdate = true;
        } else geom.setAttribute('position', new THREE.Float32BufferAttribute(outPos, 3));
        if (outColors) {
          if (geom.attributes.color?.array.length === outColors.length) {
            geom.attributes.color.array.set(outColors);
            geom.attributes.color.needsUpdate = true;
          } else geom.setAttribute('color', new THREE.Float32BufferAttribute(outColors, 3));
        } else geom.deleteAttribute('color');
        if (geom.attributes.contour?.array.length === contour.length) {
          geom.attributes.contour.array.set(contour); geom.attributes.contour.needsUpdate=true;
        } else geom.setAttribute('contour',new THREE.BufferAttribute(contour,2));
        geom.computeBoundingBox();
        geom.computeBoundingSphere();
      };
      if (reusable) {
        update(existing.geometry);

        timings.reusedGeometry = true;
      } else {
        this._disposeGroup(this.meshGroup);
        this._disposeGroup(this.wireframeGroup);
        const geom = new THREE.BufferGeometry();
        update(geom);
        geom.setIndex(new THREE.BufferAttribute(new Uint32Array(indices), 1));
        const mesh = new THREE.Mesh(geom, createContourMaterial());
        this.meshGroup.add(mesh);
      }
      const mesh=this.meshGroup.children[0];
      configureContour(mesh.material,!!fieldVals,colormap,fieldMax>fieldMin ? this.contourBands : 0);
      // Only visible surface element perimeters; no triangulation diagonals.
      if (!reusable || !this.wireframeGroup.children.length) {
      const visibleEdges=new Set();
      for(let i=0;i<indices.length;i+=3) for(let j=0;j<3;j++) {
        const a=indices[i+j], b=indices[i+(j+1)%3];
        visibleEdges.add(a<b?`${a},${b}`:`${b},${a}`);
      }
      const meshEdges=[];
      if(vtuResult.meshEdges) {
        for(let i=0;i<vtuResult.meshEdges.length;i+=2) {
          const a=vtuResult.meshEdges[i],b=vtuResult.meshEdges[i+1];
          if(visibleEdges.has(a<b?`${a},${b}`:`${b},${a}`)) meshEdges.push(a,b);
        }
      } else for(const edge of visibleEdges) meshEdges.push(...edge.split(',').map(Number));
      this._updateEdges(this.wireframeGroup, mesh.geometry.attributes.position, meshEdges, 0x142536, .45);
      } else this.wireframeGroup.children[0].geometry.computeBoundingSphere();
      if (positionsChanged || !this.edgeGroup.children.length)
      this._updateEdges(this.edgeGroup, mesh.geometry.attributes.position, featureEdges(outPos,indices), 0x07101a, .9);
      this.edgeGroup.visible=this._edgesVisible;
      hasGeom = true;
    }

    if (!indices.length) {
      this._disposeGroup(this.meshGroup);
      this._disposeGroup(this.wireframeGroup);
      this._disposeGroup(this.edgeGroup);
    }
    // --- Lines (beams/trusses) ---
    if (lines.length > 0) {
      const existing = this._lineGroup.children[0];
      const oldIndex = existing?.geometry.index?.array;
      const reuse = existing && existing.geometry.attributes.position.count === nNodes &&
        oldIndex?.length === lines.length && oldIndex.every((v,i)=>v===lines[i]);
      if (!reuse) this._disposeGroup(this._lineGroup);
      const geometry = reuse ? existing.geometry : new THREE.BufferGeometry();
      for (const [name, values] of [['position',positions],['color',outColors]]) {
        if (!values) {geometry.deleteAttribute(name); continue;}
        if (geometry.attributes[name]?.array.length === values.length) {
          geometry.attributes[name].array.set(values);
          geometry.attributes[name].needsUpdate = true;
        } else geometry.setAttribute(name,new THREE.Float32BufferAttribute(values,3));
      }
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
      if (reuse) {
        existing.material.vertexColors = !!outColors;
        existing.material.color.set(outColors ? 0xffffff : 0x88ccff);
        existing.material.needsUpdate = true;
        timings.reusedGeometry = true;
      } else {
        geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(lines),1));
        this._lineGroup.add(new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({
          vertexColors:!!outColors,color:outColors ? 0xffffff : 0x88ccff,
        })));
        this.scene.add(this._lineGroup);
      }
      hasGeom = true;
    } else this._disposeGroup(this._lineGroup);

    if (!hasGeom) return;
    if (boundsMin) allBounds.set(new THREE.Vector3(...boundsMin), new THREE.Vector3(...boundsMax));
    this._applyClipping();
    this.setWireframe(this._wireframeVisible || false);
    this.setOpacity(this._opacity ?? 1);
    this.lastBuildMs = performance.now() - started;
    this.lastTimings = {...timings, totalMs: this.lastBuildMs,
      sceneMs: Math.max(0, this.lastBuildMs - timings.acquireMs),
      retainedCacheBytes: this._parsedFrames?.bytes || 0};
    if (prefetch) {
      const epoch = this._prefetchEpoch;
      setTimeout(() => { if (epoch === this._prefetchEpoch && loadVersion === this._loadVersion) prefetch(); }, 100);
    }
    if (!preserveCamera) this._fitCamera(allBounds);
    this.requestRender();
    return { bounds: allBounds };
  }  getVtuStats() {
    if (!this._lastVtuResult) return { nodes: 0, elements: 0 };
    return {
      nodes: Math.floor(this._lastVtuResult.positions.length / 3),
      elements: this._lastVtuResult.cellCount ?? (this._lastVtuResult.cells || []).length,
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
    this.gridHelper.visible = false;
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
    this._clippingEnabled = !this._clippingEnabled;
    this._applyClipping();
  }

  setClippingEnabled(enabled) {
    this._clippingEnabled = enabled;
    this._applyClipping();
  }

  setClippingPosition(value) {
    this._clippingPosition = value;
    if (this.clipPlane) {
      this.clipPlane.constant = value;
    }
    if (this._clippingEnabled) {
      this._applyClipping();
    }
  }

  _applyClipping() {
    if (!this.clipPlane) {
      this.clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    }
    this.clipPlane.constant = this._clippingPosition;
    const enabled = this._clippingEnabled;
    for (const group of [this.meshGroup,this.wireframeGroup,this.edgeGroup,this._lineGroup]) {
      group?.children.forEach(c => {if(c.material) c.material.clippingPlanes=enabled?[this.clipPlane]:[];});
    }
    this.renderer.localClippingEnabled = true;
    this.requestRender();
  }

  isClippingEnabled() {
    return this._clippingEnabled;
  }

  getClippingPosition() {
    return this._clippingPosition;
  }

  // ── Opacity ──

  setOpacity(opacity) {
    this._opacity = opacity;
    this.requestRender();
    this.meshGroup.children.forEach(c => {
      if (c.isMesh) {
        c.material.transparent = opacity < 1;
        c.material.opacity = opacity;
        c.material.needsUpdate = true;
      }
    });
    for(const group of [this.wireframeGroup,this.edgeGroup]) group.children.forEach(c=>{
      c.material.opacity=(group === this.edgeGroup ? .9 : .45)*opacity;
    });
  }

  _updateEdges(group, position, indices, color, opacity) {
    let line=group.children[0];
    if(!line) {
      line=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({
        color, transparent:true, opacity, depthWrite:false, toneMapped:false}));
      group.add(line);
    }
    line.geometry.setAttribute('position',position);
    const old=line.geometry.index;
    if(!old || old.count!==indices.length || !old.array.every((v,i)=>v===indices[i]))
      line.geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(indices),1));
    line.geometry.computeBoundingSphere();
  }

  setFeatureEdges(visible) {
    this._edgesVisible=visible; this.edgeGroup.visible=visible; this.requestRender();
  }

  setWireframe(visible) {
    this.requestRender();
    this._wireframeVisible = visible;
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
    if (w <= 0 || h <= 0) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
   this.renderer.setSize(w, h);
   if (this.labelRenderer) this.labelRenderer.setSize(w, h);
    if (this.axisRenderer) {
      this.axisRenderer.setSize(170, 170);
    }
    this.controls?.handleResize();
    this.requestRender();
  }

  requestRender() {
    this._needsRender = true;
  }

  _animate() {
    if (this._disposed) return;
    this.animFrameId = requestAnimationFrame(() => this._animate());
    this.controls.update();
    // Keep sampling controls, but leave both WebGL contexts idle when unchanged.
    if (!this._needsRender) return;
    this._needsRender = false;
    this.renderer.render(this.scene, this.camera);

   // Render axis indicator (top-right corner)
   if (this.axisGroup && this.axisCamera) {
     this.axisGroup.quaternion.copy(this.camera.quaternion);
      this.axisRenderer.render(this.axisScene, this.axisCamera);

      // Update HTML label positions via 3D-to-screen projection
      if (this._axisLabelElements) {
        const sz = 170;
        const len = 1.6;
        const offset = 0.3;
        for (let i = 0; i < 3; i++) {
          const p = this._axisPoint.set(
            this._axisDirs[i][0] * (len + offset),
            this._axisDirs[i][1] * (len + offset),
            this._axisDirs[i][2] * (len + offset)
          );
          // Apply the axis group rotation (mirrors main camera) so labels follow the view
          p.applyQuaternion(this.axisGroup.quaternion);
          p.project(this.axisCamera);
          const x = (p.x * 0.5 + 0.5) * sz;
          const y = (-p.y * 0.5 + 0.5) * sz;
          this._axisLabelElements[i].style.left = x + 'px';
          this._axisLabelElements[i].style.top = y + 'px';
        }
      }
    }

    // CSS2D labels
    if (this.labelRenderer) {
      this.labelRenderer.render(this.scene, this.camera);
    }
  }
}

