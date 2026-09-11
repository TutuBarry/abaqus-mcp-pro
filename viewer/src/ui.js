import { exportFromODB, loadExportedJson, getExportedJsonPath } from './odbexport.js';
import { drawColormapOnCanvas, fmtNum } from './colormaps.js';

/**
 * UI controller. Attaches event listeners and updates UI state.
 */
export class UIController {
  constructor(viewer) {
    this.viewer = viewer;
    this._playing = false;
    this._playTimer = null;
    this._clipActive = false;

    this._setupSidebarToggle();
    this._setupFileInput();
    this._setupODBExport();
    this._setupToolbar();
    this._setupAnimBar();
    this._setupKeyboard();
    this._setupDragDrop();
    this._setupSectionToggle();
    this._setupToasts();
  }

  // ── Sidebar Toggle ──

  _setupSidebarToggle() {
    const toggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      toggle.textContent = sidebar.classList.contains('collapsed') ? '\u25B6' : '\u25C0';
      setTimeout(() => this.viewer._handleResize(), 300);
    });
  }

  // ── Section Toggle (collapsible sidebar sections) ──

  _setupSectionToggle() {
    document.querySelectorAll('.section-header[data-toggle]').forEach(header => {
      header.addEventListener('click', () => {
        const target = document.getElementById(header.dataset.toggle);
        if (target) target.classList.toggle('collapsed');
      });
    });
  }

  // ── File Input ──

  _setupFileInput() {
    const fileInput = document.getElementById('file-input');
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      await this._loadModelFile(file);
    });
  }

  async _loadModelFile(file) {
    try {
      const text = await file.text();
      const modelData = JSON.parse(text);
      // Determine base URL from file path for VTP resolution
      const baseUrl = URL.createObjectURL(new Blob()) + '/../'; // fallback
      // Use the directory containing the JSON as base URL
      // For File API we need to construct relative paths differently
      await this.viewer.loadModel(modelData, location.href);

      // Try to resolve VTP files relative to the JSON's location
      const dir = file.name.substring(0, file.name.lastIndexOf('/') + 1);
      const frames = modelData.frames || [];
      // Load VTPs from the same directory as the JSON
      for (const frame of frames) {
        if (frame.vtp_file) {
          const { loadVTP } = await import('./vtkparser.js');
          // For File API, we can't easily fetch relative VTPs.
          // Prefer loading from same server path.
          try {
            const vtpUrl = frame.vtp_file;
            this.viewer.vtpDataCache[frame.frame] = await loadVTP(vtpUrl, location.href);
          } catch (e) {
            console.warn(`VTP load skipped for frame ${frame.frame}:`, e.message);
          }
        }
      }
      this.viewer._rebuildScene();
      this._updateAll(modelData);
    } catch (e) {
      console.error('Load failed:', e);
      alert('Parse error: ' + e.message);
    }
  }

  // ── ODB Export ──

  _setupODBExport() {
    const exportBtn = document.getElementById('export-btn');
    const odbInput = document.getElementById('odb-path');
    const statusEl = document.getElementById('export-status');
    const progressBar = document.getElementById('export-progress-bar');
    const decimateRatio = document.getElementById('decimate-ratio');
    const decimateLabel = document.getElementById('decimate-label');
    const loadArea = document.getElementById('load-exported');
    const loadBtn = document.getElementById('load-exported-btn');

    decimateRatio?.addEventListener('input', () => {
      decimateLabel.textContent = decimateRatio.value;
    });

    const doExport = async () => {
      const odbPath = odbInput.value.trim();
      if (!odbPath) {
        statusEl.textContent = 'Please enter an ODB path';
        statusEl.className = 'error';
        return;
      }

      exportBtn.disabled = true;
      statusEl.textContent = 'Exporting from ODB...';
      statusEl.className = '';
      progressBar.style.width = '30%';
      progressBar.textContent = '30%';
      progressBar.className = '';
      loadArea.style.display = 'none';

      try {
        const result = await exportFromODB(odbPath, {
          export_v2: document.getElementById('export-format')?.value === 'v2',
          deformation_scale: parseFloat(document.getElementById('deform-scale')?.value || '1.0'),
        });

        progressBar.style.width = '100%';
        progressBar.textContent = '100%';
        progressBar.className = 'done';

        statusEl.textContent = `Exported: ${result.node_count.toLocaleString()} nodes, ${result.elem_count.toLocaleString()} elements, ${result.frame_count} frames`;
        statusEl.className = 'success';
        loadArea.style.display = 'block';

        // Auto-load
        try {
          const data = await loadExportedJson();
          const fname = getExportedJsonPath().split(/[\\/]/).pop();
          await this.viewer.loadModel(data, location.href);
          this._updateAll(data);
        } catch (e) {
          console.warn('Auto-load failed:', e);
        }
      } catch (err) {
        statusEl.textContent = 'Export failed: ' + err.message;
        statusEl.className = 'error';
        progressBar.style.width = '0%';
      } finally {
        exportBtn.disabled = false;
      }
    };

    exportBtn.addEventListener('click', doExport);
    odbInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doExport();
    });

    loadBtn?.addEventListener('click', async () => {
      try {
        const data = await loadExportedJson();
        await this.viewer.loadModel(data, location.href);
        this._updateAll(data);
      } catch (e) {
        console.error('Load exported failed:', e);
      }
    });
  }

  // ── Toolbar ──

  _setupToolbar() {
    const viewer = this.viewer;

    document.getElementById('btn-wireframe').addEventListener('click', () => {
      viewer.setWireframe(!viewer.wireframeVisible);
      document.getElementById('btn-wireframe').classList.toggle('active', viewer.wireframeVisible);
    });

    document.getElementById('btn-deformed').addEventListener('click', () => {
      viewer.setDeformed(!viewer.deformedMode);
      document.getElementById('btn-deformed').classList.toggle('active', viewer.deformedMode);
      this._updateLegend();
    });

    const deformScale = document.getElementById('deform-scale');
    const deformScaleVal = document.getElementById('deform-scale-val');
    deformScale?.addEventListener('input', () => {
      const val = parseFloat(deformScale.value);
      deformScaleVal.textContent = val.toFixed(1);
      viewer.setDeformScale(val);
    });

    document.getElementById('btn-reset').addEventListener('click', () => viewer.fitView());
    document.getElementById('btn-top').addEventListener('click', () => viewer.setView('top'));
    document.getElementById('btn-front').addEventListener('click', () => viewer.setView('front'));
    document.getElementById('btn-right').addEventListener('click', () => viewer.setView('right'));

    // Clipping
    const clipBtn = document.getElementById('btn-clip');
    const clipControls = document.getElementById('clip-controls');
    const clipSlider = document.getElementById('clip-slider');
    const clipDir = document.getElementById('clip-dir');

    clipBtn?.addEventListener('click', () => {
      this._clipActive = !this._clipActive;
      clipBtn.classList.toggle('active', this._clipActive);
      clipControls.classList.toggle('hidden', !this._clipActive);
      if (!this._clipActive) {
        viewer._clearClipping();
      } else {
        viewer.enableClipping(clipDir.value, parseFloat(clipSlider.value));
      }
    });

    clipSlider?.addEventListener('input', () => {
      if (this._clipActive) {
        viewer.enableClipping(clipDir.value, parseFloat(clipSlider.value));
      }
    });

    clipDir?.addEventListener('change', () => {
      if (this._clipActive) {
        viewer.enableClipping(clipDir.value, parseFloat(clipSlider.value));
      }
    });

    // Measurement
    const measureBtn = document.getElementById('btn-measure');
    let measureActive = false;
    measureBtn?.addEventListener('click', () => {
      measureActive = !measureActive;
      measureBtn.classList.toggle('active', measureActive);
      // Raycaster measurement would go here
    });

    // Screenshot
    document.getElementById('btn-screenshot').addEventListener('click', () => viewer.screenshot());

    // Field select
    const fieldSelect = document.getElementById('field-select');
    fieldSelect?.addEventListener('change', () => {
      const data = viewer.currentData;
      const fields = data?.fields || [];
      const field = fields[fieldSelect.selectedIndex] || null;
      viewer.setField(field);
      this._updateLegend();
    });

    // Colormap select
    const colormapSelect = document.getElementById('colormap-select');
    colormapSelect?.addEventListener('change', () => {
      viewer.setColormap(colormapSelect.value);
      this._updateLegend();
    });
  }

  // ── Animation Bar ──

  _setupAnimBar() {
    const slider = document.getElementById('frame-slider');

    document.getElementById('btn-prev').addEventListener('click', () => {
      if (this.viewer.currentData) {
        this.viewer.setFrame(0);
        this._updateAnimBar();
        this._updateLegend();
      }
    });

    document.getElementById('btn-play').addEventListener('click', () => this._togglePlay());

    document.getElementById('btn-next').addEventListener('click', () => {
      if (this.viewer.currentData) {
        const frames = this.viewer.currentData.frames || [];
        this.viewer.setFrame(frames.length - 1);
        this._updateAnimBar();
        this._updateLegend();
      }
    });

    slider.addEventListener('input', () => {
      const idx = parseInt(slider.value, 10);
      this.viewer.setFrame(idx);
      this._updateAnimBar();
      this._updateLegend();
    });
  }

  _togglePlay() {
    if (!this.viewer.currentData || (this.viewer.currentData.frames || []).length <= 1) return;
    this._playing = !this._playing;
    const btn = document.getElementById('btn-play');
    btn.textContent = this._playing ? '\u23F8' : '\u25B6';
    if (this._playing) {
      this._playTimer = setInterval(() => {
        const frames = this.viewer.currentData.frames || [];
        const next = this.viewer.currentFrame >= frames.length - 1 ? 0 : this.viewer.currentFrame + 1;
        this.viewer.setFrame(next);
        this._updateAnimBar();
        this._updateLegend();
      }, 200);
    } else {
      if (this._playTimer) {
        clearInterval(this._playTimer);
        this._playTimer = null;
      }
    }
  }

  // ── Keyboard ──

  _setupKeyboard() {
    window.addEventListener('keydown', (e) => {
      switch (e.key.toLowerCase()) {
        case 'w':
          document.getElementById('btn-wireframe').click();
          break;
        case 'd':
          document.getElementById('btn-deformed').click();
          break;
        case 'r':
          document.getElementById('btn-reset').click();
          break;
        case 'm':
          document.getElementById('btn-measure').click();
          break;
        case 's':
          document.getElementById('btn-screenshot').click();
          break;
        case ' ':
          e.preventDefault();
          this._togglePlay();
          break;
        case 'arrowleft':
          if (this.viewer.currentData) {
            this.viewer.setFrame(this.viewer.currentFrame - 1);
            this._updateAnimBar();
            this._updateLegend();
          }
          break;
        case 'arrowright':
          if (this.viewer.currentData) {
            this.viewer.setFrame(this.viewer.currentFrame + 1);
            this._updateAnimBar();
            this._updateLegend();
          }
          break;
      }
    });
  }

  // ── Drag & Drop ──

  _setupDragDrop() {
    const viewport = document.getElementById('viewport');
    viewport.addEventListener('dragover', (e) => e.preventDefault());
    viewport.addEventListener('drop', async (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) await this._loadModelFile(file);
    });
  }

  // ── Toast Notifications ──

  _setupToasts() {
    // Create toast container if not exists
    if (!document.getElementById('toast-container')) {
      const container = document.createElement('div');
      container.id = 'toast-container';
      container.style.cssText = 'position:fixed;top:12px;right:12px;z-index:1000;display:flex;flex-direction:column;gap:6px;pointer-events:none';
      document.body.appendChild(container);
    }
    
    // Register viewer toast callbacks
    const viewer = this.viewer;
    viewer.onToast(function(type, msg) {
      // Import and use showToast from viewer3d
      import('./viewer3d.js').then(function(mod) {
        mod.showToast(type, msg);
      });
    });
  }

  // ── UI Update Methods ──

  _updateAll(data) {
    this._updateInfo(data);
    this._updateTree(data);
    this._updateFieldSelect(data);
    this._updateAnimBar();
    this._updateLegend();
  }

  _updateInfo(data) {
    let nodes = data.num_nodes || 0;
    let elems = data.num_elements || 0;
    const frames = (data.frames || []).length;
    
    // For v2.0 (VTP format), get actual rendered counts from viewer
    if (data.format_version === '2.0' || data.format_version === 2.0) {
      const stats = this.viewer.getVtpStats();
      if (stats) {
        nodes = stats.nodes;
        elems = stats.elements;
      }
    }
    
    document.getElementById('info-nodes').textContent = nodes.toLocaleString();
    document.getElementById('info-elems').textContent = elems.toLocaleString();
    document.getElementById('info-frames').textContent = frames.toLocaleString();
  }

  _updateTree(data) {
    const tree = document.getElementById('tree');
    tree.innerHTML = '';

    const addSection = (title) => {
      const el = document.createElement('div');
      el.className = 'tree-section';
      el.textContent = title;
      tree.appendChild(el);
    };

    const addItem = (label, onClick, isActive) => {
      const el = document.createElement('div');
      el.className = 'tree-item' + (isActive ? ' active' : '');
      el.textContent = label;
      if (onClick) el.addEventListener('click', onClick);
      tree.appendChild(el);
      return el;
    };

    addSection('Model');
    addItem(`Nodes: ${(data.num_nodes || 0).toLocaleString()}`);
    addItem(`Elements: ${(data.num_elements || 0).toLocaleString()}`);

    if (data.model_name) addItem(`Name: ${data.model_name}`);

    const fields = data.fields || [];
    if (fields.length > 0) {
      addSection('Fields');
      for (const f of fields) {
        addItem(f.label || f.name || f.key, () => {
          this.viewer.setField(f);
          document.querySelectorAll('#tree .tree-item.active').forEach(el => el.classList.remove('active'));
          // Re-render tree to show active state
          this._updateTree(data);
          this._updateLegend();
        }, this.viewer.currentField === f);
      }
    }

    const steps = data.steps || [];
    if (steps.length > 0) {
      addSection('Steps');
      for (const s of steps) {
        addItem(s.label || s.name || 'Step');
      }
    }

    addSection('Info');
    if (data.job_name) addItem(`Job: ${data.job_name}`);
    if (data.abaqus_version) addItem(`Abaqus: ${data.abaqus_version}`);
    if (data.export_time) addItem(`Exported: ${data.export_time}`);
  }

  _updateFieldSelect(data) {
    const select = document.getElementById('field-select');
    if (!select) return;
    const fields = data?.fields || [];
    select.innerHTML = '';
    fields.forEach((f, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = f.label || f.name || f.key || `Field ${i}`;
      select.appendChild(opt);
    });
  }

  _updateAnimBar() {
    const bar = document.getElementById('anim-bar');
    const data = this.viewer.currentData;
    const frames = data?.frames || [];

    if (frames.length <= 1) {
      bar.classList.add('hidden');
      return;
    }

    bar.classList.remove('hidden');
    const slider = document.getElementById('frame-slider');
    slider.max = frames.length - 1;
    slider.value = this.viewer.currentFrame;
    document.getElementById('frame-label').textContent =
      `${this.viewer.currentFrame + 1} / ${frames.length}`;

    const frame = frames[this.viewer.currentFrame];
    if (frame?.time !== undefined) {
      document.getElementById('frame-time').textContent =
        `t=${parseFloat(frame.time.toPrecision(4))}`;
    }
  }

  _updateLegend() {
    const canvas = document.getElementById('legend-canvas');
    const titleEl = document.getElementById('legend-title');
    const minEl = document.getElementById('legend-min');
    const maxEl = document.getElementById('legend-max');

    const field = this.viewer.currentField;
    const range = this.viewer.getFieldRange();

    if (!field || range.min === undefined) {
      titleEl.textContent = 'No field';
      minEl.textContent = '0';
      maxEl.textContent = '0';
      return;
    }

    const unit = field.unit || '';
    titleEl.textContent = `${field.label || field.name || 'Field'}${unit ? ' (' + unit + ')' : ''}`;
    drawColormapOnCanvas(canvas, this.viewer.colormapName, 200, 16);
    minEl.textContent = fmtNum(range.min);
    maxEl.textContent = fmtNum(range.max);
  }
}
