import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { sampleColormap, fmtNum } from './colormaps.js';

/**
 * Core 3D viewer engine.
 * Manages Three.js scene, camera, renderer, controls, and mesh rendering.
 */
export class Viewer3D {
  constructor(container) {
    this.container = container;

    // Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0d1117);

    // Camera
    const rect = container.getBoundingClientRect();
    this.camera = new THREE.PerspectiveCamera(45, rect.width / rect.height, 0.1, 10000);
    this.camera.position.set(1, 0.8, 1.5);

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(rect.width, rect.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);

    // Controls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;

    // Grid
    this.gridHelper = new THREE.GridHelper(5, 20, 0x30363d, 0x21262d);
    this.scene.add(this.gridHelper);

    // Lights
    this.scene.add(new THREE.AmbientLight(0x404060, 2.5));
    const d1 = new THREE.DirectionalLight(0xffffff, 1.5);
    d1.position.set(1, 1, 1);
    this.scene.add(d1);
    const d2 = new THREE.DirectionalLight(0xffffff, 0.8);
    d2.position.set(-0.5, -0.3, -0.8);
    this.scene.add(d2);

    // Groups
    this.meshGroup = new THREE.Group();
    this.wireframeGroup = new THREE.Group();
    this.scene.add(this.meshGroup);
    this.scene.add(this.wireframeGroup);

    // State
    this.currentData = null;
    this.currentFrame = 0;
    this.currentField = null;
    this.deformedMode = true;
    this.wireframeVisible = false;
    this.deformScale = 1.0;
    this.colormapName = 'jet';
    this.vtpDataCache = {};
    this.modelBaseUrl = '';

    // Resize
    this._onResize = this._handleResize.bind(this);
    window.addEventListener('resize', this._onResize);

    // Start render loop
    this._animate();
  }

  destroy() {
    window.removeEventListener('resize', this._onResize);
    this.renderer.dispose();
    this.container.removeChild(this.renderer.domElement);
  }

  _handleResize() {
    const rect = this.container.getBoundingClientRect();
    this.camera.aspect = rect.width / rect.height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(rect.width, rect.height);
  }

  _animate() {
    requestAnimationFrame(() => this._animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  /**
   * Load model.json and all frame VTP files into the viewer.
   * modelData: parsed JSON object
   * baseUrl: base URL for resolving relative VTP paths
   */
  async loadModel(modelData, baseUrl) {
    this.currentData = modelData;
    this.modelBaseUrl = baseUrl || '';
    this.vtpDataCache = {};
    this.currentFrame = 0;

    // Set up field selector
    const fields = modelData.fields || [];
    this.currentField = fields.length > 0 ? fields[0] : null;

    // Preload all VTPs
    const frames = modelData.frames || [];
    for (const frame of frames) {
      if (frame.vtp_file && !this.vtpDataCache[frame.frame]) {
        try {
          const { loadVTP } = await import('./vtkparser.js');
          const vtpUrl = new URL(frame.vtp_file, baseUrl).href;
          this.vtpDataCache[frame.frame] = await loadVTP(frame.vtp_file, baseUrl);
        } catch (e) {
          console.warn(`Failed to load VTP frame ${frame.frame}:`, e);
        }
      }
    }

    this._rebuildScene();
    return modelData;
  }

  /**
   * Rebuild the 3D scene for the current frame and field.
   */
  _rebuildScene() {
    // Clear old meshes
    this._clearMeshes();

    const data = this.currentData;
    if (!data) return;

    const vtpData = this.vtpDataCache[this.currentFrame];
    this._lastVtpResult = vtpData;
    if (!vtpData) return;
    if (vtpData.triangles.length === 0) return;

    const geom = new THREE.BufferGeometry();

    // Points
    const positions = new Float32Array(vtpData.points);
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Triangles
    geom.setIndex(new THREE.BufferAttribute(vtpData.triangles, 1));

    // Colors from field data
    const fieldName = this.currentField ? (this.currentField.name || this.currentField.key) : null;
    let colors = null;
    let fieldMin = 0, fieldMax = 1;

    if (fieldName && vtpData.pointData[fieldName]) {
      const vals = vtpData.pointData[fieldName];
      fieldMin = Infinity;
      fieldMax = -Infinity;
      // Apply deformation displacement if active
      if (this.deformedMode && vtpData.pointData['U'] && this.deformScale > 0) {
        const disp = vtpData.pointData['U'];
        const posAttr = geom.attributes.position;
        const array = posAttr.array;
        const scale = this.deformScale * (data.deformation_scale_factor || 1);
        for (let i = 0; i < posAttr.count; i++) {
          const i3 = i * 3;
          array[i3] = vtpData.points[i3] + disp[i3 * 3] * scale;
          array[i3 + 1] = vtpData.points[i3 + 1] + disp[i3 * 3 + 1] * scale;
          array[i3 + 2] = vtpData.points[i3 + 2] + disp[i3 * 3 + 2] * scale;
        }
        posAttr.needsUpdate = true;
      } else {
        // Reset to original positions
        const posAttr = geom.attributes.position;
        const array = posAttr.array;
        for (let i = 0; i < posAttr.count; i++) {
          array[i] = vtpData.points[i];
        }
        posAttr.needsUpdate = true;
      }

      // Compute min/max for field values
      for (let i = 0; i < vals.length; i++) {
        const v = vals[i];
        if (v < fieldMin) fieldMin = v;
        if (v > fieldMax) fieldMax = v;
      }

      // Store field range
      if (fieldMin < Infinity) {
        this._lastFieldMin = fieldMin;
        this._lastFieldMax = fieldMax;
      }

      // Build vertex colors
      colors = new Float32Array(vals.length * 3);
      const range = fieldMax - fieldMin;
      for (let i = 0; i < vals.length; i++) {
        const t = range > 1e-12 ? (vals[i] - fieldMin) / range : 0.5;
        const [r, g, b] = sampleColormap(this.colormapName, t);
        colors[i * 3] = r;
        colors[i * 3 + 1] = g;
        colors[i * 3 + 2] = b;
      }
      geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    } else {
      // No field data
      this._lastFieldMin = 0;
      this._lastFieldMax = 1;
      if (this.deformedMode && vtpData.pointData['U'] && this.deformScale > 0) {
        const disp = vtpData.pointData['U'];
        const posAttr = geom.attributes.position;
        const array = posAttr.array;
        const scale = this.deformScale * (data.deformation_scale_factor || 1);
        for (let i = 0; i < posAttr.count; i++) {
          const i3 = i * 3;
          array[i3] = vtpData.points[i3] + disp[i3 * 3] * scale;
          array[i3 + 1] = vtpData.points[i3 + 1] + disp[i3 * 3 + 1] * scale;
          array[i3 + 2] = vtpData.points[i3 + 2] + disp[i3 * 3 + 2] * scale;
        }
        posAttr.needsUpdate = true;
      }
    }

    geom.computeVertexNormals();

    const hasColors = colors !== null;
    const mat = new THREE.MeshPhongMaterial({
      vertexColors: hasColors,
      color: hasColors ? 0xffffff : 0x4488cc,
      specular: 0x111111,
      shininess: 30,
      side: THREE.DoubleSide,
    });

    const mesh = new THREE.Mesh(geom, mat);
    this.meshGroup.add(mesh);

    // Wireframe
    const wfMat = new THREE.MeshBasicMaterial({
      color: 0xcccccc,
      wireframe: true,
      transparent: true,
      opacity: 0.3,
    });
    const wf = new THREE.Mesh(geom.clone(), wfMat);
    wf.visible = this.wireframeVisible;
    this.wireframeGroup.add(wf);

    // Auto-fit camera on first load
    this._fitCamera();

    // Store field range for legend
    this._lastFieldMin = fieldMin;
    this._lastFieldMax = fieldMax;

    return { fieldMin, fieldMax };
  }

  _clearMeshes() {
    const disposeGroup = (group) => {
      while (group.children.length > 0) {
        const child = group.children[0];
        if (child.geometry) child.geometry.dispose();
        if (child.material) child.material.dispose();
        group.remove(child);
      }
    };
    disposeGroup(this.meshGroup);
    disposeGroup(this.wireframeGroup);
  }

  _fitCamera() {
    const box = new THREE.Box3().setFromObject(this.meshGroup);
    if (box.isEmpty()) return;

    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    const s = size || 1;

    this.camera.position.copy(
      center.clone().add(new THREE.Vector3(s * 0.8, s * 0.6, s * 1.0))
    );
    this.controls.target.copy(center);
    this.controls.update();

    // Update grid
    this.scene.remove(this.gridHelper);
    this.gridHelper.geometry.dispose();
    this.gridHelper.material.dispose();
    const gridSize = Math.pow(10, Math.ceil(Math.log10(s * 0.7)));
    this.gridHelper = new THREE.GridHelper(gridSize, 20, 0x30363d, 0x21262d);
    this.scene.add(this.gridHelper);
  }

  // ── Public API ──

  setFrame(frameIdx) {
    if (!this.currentData) return;
    const frames = this.currentData.frames || [];
    this.currentFrame = Math.max(0, Math.min(frameIdx, frames.length - 1));
    this._rebuildScene();
  }

  setField(field) {
    this.currentField = field;
    this._rebuildScene();
  }

  setColormap(name) {
    this.colormapName = name;
    this._rebuildScene();
  }

  setDeformed(on) {
    this.deformedMode = on;
    this._rebuildScene();
  }

  setDeformScale(scale) {
    this.deformScale = scale;
    if (this.deformedMode) this._rebuildScene();
  }

  setWireframe(on) {
    this.wireframeVisible = on;
    this.wireframeGroup.children.forEach(c => { c.visible = on; });
  }

  fitView() {
    this._fitCamera();
  }

  setView(direction) {
    const box = new THREE.Box3().setFromObject(this.meshGroup);
    if (box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3());
    const s = box.isEmpty() ? 1 : box.getSize(new THREE.Vector3()).length();
    const dist = s * 1.5;
    switch (direction) {
      case 'top': this.camera.position.set(c.x, c.y + dist, c.z + 0.01); break;
      case 'front': this.camera.position.set(c.x, c.y, c.z + dist); break;
      case 'right': this.camera.position.set(c.x + dist, c.y, c.z); break;
    }
    this.controls.target.copy(c);
    this.controls.update();
  }

  getFieldRange() {
    return { min: this._lastFieldMin, max: this._lastFieldMax };
  }

  screenshot() {
    this.renderer.render(this.scene, this.camera);
    const link = document.createElement('a');
    link.download = `abaqus-screenshot-${Date.now()}.png`;
    link.href = this.renderer.domElement.toDataURL('image/png');
    link.click();
  }

  enableClipping(direction, position) {
    this._clearClipping();
    if (!direction) return;
    const dirMap = {
      'x': new THREE.Vector3(1, 0, 0),
      '-x': new THREE.Vector3(-1, 0, 0),
      'y': new THREE.Vector3(0, 1, 0),
      '-y': new THREE.Vector3(0, -1, 0),
      'z': new THREE.Vector3(0, 0, 1),
      '-z': new THREE.Vector3(0, 0, -1),
    };
    const normal = dirMap[direction];
    if (!normal) return;

    // Apply clipping to all meshes
    const clipPlane = new THREE.Plane(normal, -position);
    this.meshGroup.children.forEach(child => {
      if (child.material) {
        child.material.clippingPlanes = [clipPlane];
        child.material.clipShadows = true;
        child.material.needsUpdate = true;
      }
    });
    this.renderer.localClippingEnabled = true;
  }

  _clearClipping() {
    this.meshGroup.children.forEach(child => {
      if (child.material) {
        child.material.clippingPlanes = [];
        child.material.needsUpdate = true;
      }
    });
    this.renderer.localClippingEnabled = false;
  }

  /**
   * Register a toast callback function.
   * The callback receives (type, message) where type is "success", "error", or "info".
   * Returns an unregister function.
   */
  onToast(callback) {
    this._toastCallbacks.push(callback);
    return () => {
      const idx = this._toastCallbacks.indexOf(callback);
      if (idx >= 0) this._toastCallbacks.splice(idx, 1);
    };
  }
}

/**
 * Global toast notification helper.
 * Creates a DOM-based toast that auto-dismisses.
 */
export function showToast(type, message, duration) {
  if (duration === undefined) duration = 4000;
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(function() {
    el.classList.add('toast-out');
    setTimeout(function() { el.remove(); }, 300);
  }, duration);
}

