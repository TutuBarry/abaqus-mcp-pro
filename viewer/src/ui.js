/**
 * UIController — manages DOM bindings, sidebar panels, toolbar, animation, toast.
 */

import { sampleColormap, colormapToCSS, getColormapNames, COLORMAPS } from "./colormaps.js";
import { MeasureTool } from './measure.js';
import { ProgressLoader } from './loader.js';

export class UIController {
  constructor(viewer, state) {
    this.viewer = viewer;
    this.state = state;
    this.panels = { file: false, odb: false, display: true, fields: false, measure: false };
    this.measure = new MeasureTool(viewer);
    this.progress = new ProgressLoader('progress-overlay');
  }

  init() {
    this._bindLeftBar();
    this._bindPanels();
    this._bindFileInput();
    this._bindDragDrop();
    this._bindDisplay();
    this._bindAnimBar();
    this._bindTopBar();
    this._bindKeyboard();
    this._bindMeasureToggle();
    this._bindOpacity();
    this._bindToolbar();
    this._bindProbe();
    this._bindLoopMode();
    this._enhanceColormapPicker();
  }

  /* ── Load Sample ── */
  async loadSample(url) {
    try {
      this._updateStatus('加载示例模型...');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      this.state.data = data;
      const fmt = data.format_version || 'v1.0';
      this.state.format = fmt === '2.0' || fmt.startsWith('2.') ? 'v2.0' : 'v1.0';
      this.state.currentFrame = 0;
      this.state.currentField = (data.fields || [])[0] || null;
      this.state.deformation_scale_factor = data.deformation_scale_factor || 1.0;
      this.state.scaleFactor = data.deformation_scale_factor || 1.0;

      const opts = { frameIdx: 0, field: this.state.currentField, colormap: this.state.colormapName };
      if (this.state.format === 'v2.0') {
        await this.viewer.buildSceneFromVTP(data, opts);
      } else {
        this.viewer.buildScene(data, { ...opts, deformed: this.state.deformed, scaleFactor: this.state.scaleFactor });
      }
      this._updateAll(data);
      this._setFileBadge('悬臂梁示例');
      this._updateStatus('已加载示例模型: 悬臂梁弯曲');
      this._toast('已加载悬臂梁示例 • 多帧动画', 'info');
    } catch (e) {
      console.warn('Sample load failed:', e);
      this._updateStatus('就绪');
    }
  }

  /* ── Left Bar ── */
  _bindLeftBar() {
    const openPanel = (name) => {
      Object.keys(this.panels).forEach((k) => (this.panels[k] = false));
      this.panels[name] = true;
      this._syncPanels();
    };

    document.getElementById('lb-file').addEventListener('click', () => {
      openPanel('file');
      document.getElementById('file-input').click();
    });
    document.getElementById('lb-odb').addEventListener('click', () => openPanel('odb'));
    document.getElementById('lb-settings').addEventListener('click', () => openPanel('display'));
    document.getElementById('lb-fields').addEventListener('click', () => openPanel('fields'));
    document.getElementById('lb-measure').addEventListener('click', () => openPanel('measure'));
    document.getElementById('lb-screenshot').addEventListener('click', () => this.viewer.takeScreenshot());
    document.getElementById('lb-help').addEventListener('click', () => this._showHelp());
  }

  _showHelp() {
    const msg = [
      '快捷键:',
      '  W — 线框切换',
      '  D — 变形切换',
      '  R — 重置视角',
      '  Space — 播放/暂停',
      '  ← → — 上一帧/下一帧',
      '  ↑ / 1 — 俯视图',
      '  2 — 正视图',
      '  3 — 右视图',
      '  C — 截图',
      '  M — 测量工具',
    ].join('\n');
    this._toast(msg, 'info');
  }

  /* ── Panel toggles ── */
  _bindPanels() {
    document.querySelectorAll('.panel-header').forEach((hdr) => {
      hdr.addEventListener('click', () => {
        const name = hdr.dataset.panel;
        if (!name) return;
        this.panels[name] = !this.panels[name];
        this._syncPanels();
      });
    });
    document.getElementById('sidebar-close').addEventListener('click', () => {
      Object.keys(this.panels).forEach((k) => (this.panels[k] = false));
      this._syncPanels();
    });
  }

  _syncPanels() {
    const anyOpen = Object.values(this.panels).some((v) => v);
    document.getElementById('sidebar').classList.toggle('open', anyOpen);
    document.querySelectorAll('.panel-body').forEach((el) => el.classList.remove('closed'));
    Object.entries(this.panels).forEach(([name, open]) => {
      const body = document.getElementById('panel-body-' + name);
      if (body) body.classList.toggle('closed', !open);
    });

    // Update left bar active state
    const activeMap = { file: 'lb-file', odb: 'lb-odb', display: 'lb-settings', fields: 'lb-fields', measure: 'lb-measure' };
    document.querySelectorAll('.leftbar-btn').forEach((b) => b.classList.remove('active'));
    Object.entries(this.panels).forEach(([name, open]) => {
      if (open) {
        const id = activeMap[name];
        if (id) document.getElementById(id)?.classList.add('active');
      }
    });

    // Update title
    const titleMap = { file: '加载文件', odb: 'ODB 导出', display: '显示设置', fields: '场变量', measure: '测量工具' };
    for (const [name, open] of Object.entries(this.panels)) {
      if (open) {
        document.getElementById('sidebar-title').textContent = titleMap[name] || '设置';
        return;
      }
    }
    document.getElementById('sidebar-title').textContent = '设置';
  }

  /* ── File Input ── */
  _bindFileInput() {
    document.getElementById('file-input').addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) this._loadFile(file);
    });
  }

  async _loadFile(file) {
    try {
      const text = await file.text();
      let data;
      try { data = JSON.parse(text); } catch (_) { throw new Error('不是有效的 JSON 文件'); }
      this.state.data = data;
      const fmt = data.format_version || 'v1.0';
      this.state.format = fmt === '2.0' || fmt.startsWith('2.') ? 'v2.0' : 'v1.0';
      this.state.currentFrame = 0;
      this.state.currentField = (data.fields || [])[0] || null;
      this.state.deformation_scale_factor = data.deformation_scale_factor || 1.0;
      this.state.scaleFactor = data.deformation_scale_factor || 1.0;

      const opts = { frameIdx: 0, field: this.state.currentField, colormap: this.state.colormapName };
      if (this.state.format === 'v2.0') {
        await this.viewer.buildSceneFromVTP(data, opts);
      } else {
        this.viewer.buildScene(data, { ...opts, deformed: this.state.deformed, scaleFactor: this.state.scaleFactor });
      }
      this._updateAll(data);
      this._setFileBadge(file.name);
      this._updateStatus('已加载: ' + file.name);
      this._toast('加载成功: ' + file.name, 'success');
    } catch (e) {
      this._updateStatus('加载失败: ' + e.message);
      this._toast('加载失败: ' + e.message, 'error');
    }
  }

  /* ── Drag & drop ── */
  _bindDragDrop() {
    const vp = document.getElementById('viewport');
    const dz = document.getElementById('drop-zone');
    vp.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.remove('hidden'); });
    vp.addEventListener('dragleave', () => dz.classList.add('hidden'));
    vp.addEventListener('drop', (e) => {
      e.preventDefault();
      dz.classList.add('hidden');
      const f = e.dataTransfer.files[0];
      if (f) this._loadFile(f);
    });
  }

  /* ── Display controls ── */
  _bindDisplay() {
    document.getElementById('btn-wireframe').addEventListener('click', () => {
      this.state.wireframe = !this.state.wireframe;
      document.getElementById('btn-wireframe').classList.toggle('active', this.state.wireframe);
      this.viewer.setWireframe(this.state.wireframe);
    });
    document.getElementById('btn-deformed').addEventListener('click', () => {
      this.state.deformed = !this.state.deformed;
      document.getElementById('btn-deformed').classList.toggle('active', this.state.deformed);
      this._rebuild();
    });
    document.getElementById('btn-clip').addEventListener('click', () => {
      this.state.clipping = !this.state.clipping;
      document.getElementById('btn-clip').classList.toggle('active', this.state.clipping);
      this.viewer.toggleClipping();
    });

    const scaleSlider = document.getElementById('deform-scale');
    scaleSlider.addEventListener('input', () => {
      this.state.scaleFactor = parseFloat(scaleSlider.value);
      document.getElementById('deform-scale-val').textContent = this.state.scaleFactor.toFixed(1);
      if (this.state.deformed) this._rebuild();
    });
  }

  /* ── Opacity ── */
  _bindOpacity() {
    const slider = document.getElementById('opacity-slider');
    const val = document.getElementById('opacity-val');
    slider.addEventListener('input', () => {
      const v = parseFloat(slider.value);
      val.textContent = v.toFixed(2);
      this.viewer.setOpacity(v);
    });
  }

  /* ── Toolbar ── */
  _bindToolbar() {
    document.getElementById('btn-reset').addEventListener('click', () => this.viewer.resetCamera());
    document.getElementById('btn-top').addEventListener('click', () => this.viewer.setView('top'));
    document.getElementById('btn-front').addEventListener('click', () => this.viewer.setView('front'));
    document.getElementById('btn-right').addEventListener('click', () => this.viewer.setView('right'));
  }

  /* ── Loop mode ── */
  _bindLoopMode() {
    const btns = document.querySelectorAll('.loop-btn');
    btns.forEach(btn => {
      btn.addEventListener('click', () => {
        btns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.state.loopMode = btn.dataset.loop || 'loop';
      });
    });
  }

  /* ── Animation Bar ── */
  _bindAnimBar() {
    document.getElementById('btn-play').addEventListener('click', () => this._togglePlay());
    document.getElementById('btn-first').addEventListener('click', () => this._setFrame(0));
    document.getElementById('btn-last').addEventListener('click', () => {
      const max = this.state.data ? (this.state.data.frames || this.state.data.frame_files || []).length - 1 : 0;
      this._setFrame(max);
    });
    document.getElementById('frame-slider').addEventListener('input', (e) => this._setFrame(parseInt(e.target.value)));
  }

  _togglePlay() {
    if (!this.state._playDir) this.state._playDir = 1;
    const frames = this.state.data ? this.state.data.frames || this.state.data.frame_files || [] : [];
    if (frames.length <= 1) return;
    this.state.playing = !this.state.playing;
    const btn = document.getElementById('btn-play');
    btn.innerHTML = this.state.playing
      ? '<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
      : '<svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    if (this.state.playing) {
      this.state.playTimer = setInterval(() => {
        const max = frames.length - 1;
        const mode = this.state.loopMode || 'loop';
        if (this.state.currentFrame >= max) {
          if (mode === 'once') {
            this._togglePlay();
            return;
          } else if (mode === 'pingpong') {
            // reverse direction
            this.state._playDir = (this.state._playDir || 1) * -1;
          }
          if (mode === 'loop' || mode === 'pingpong') {
            this.state.currentFrame = this.state.currentFrame + this.state._playDir;
          }
        } else {
          this.state.currentFrame += this.state._playDir || 1;
        }
        if (this.state.currentFrame < 0) { this.state.currentFrame = 0; this.state._playDir = 1; }
        if (this.state.currentFrame > max) { this.state.currentFrame = 0; }
        this._rebuild();
        this._updateAnimBar();
      }, 200);
    } else {
      if (this.state.playTimer) { clearInterval(this.state.playTimer); this.state.playTimer = null; }
    }
  }

  _setFrame(idx) {
    const frames = this.state.data ? this.state.data.frames || this.state.data.frame_files || [] : [];
    if (frames.length === 0) return;
    this.state.currentFrame = Math.max(0, Math.min(idx, frames.length - 1));
    this._rebuild();
    this._updateAnimBar();
  }

  /* ── Colormap picker enhancement (color preview) ── */
  _enhanceColormapPicker() {
    const sel = document.getElementById('colormap-select');
    if (!sel) return;
    // Add color swatch preview next to select
    const wrapper = sel.closest('.colormap-picker');
    if (!wrapper) return;
    const preview = document.createElement('span');
    preview.style.cssText = 'display:inline-block;width:20px;height:10px;border-radius:2px;margin-left:2px;flex-shrink:0';
    wrapper.insertBefore(preview, sel.nextSibling);
    const updatePreview = () => {
      preview.style.background = colormapToCSS(sel.value);
    };
    sel.addEventListener('change', updatePreview);
    updatePreview();
  }

  /* ── Top bar ── */
  _bindTopBar() {
    document.getElementById('colormap-select').addEventListener('change', (e) => {
      this.state.colormapName = e.target.value;
      this._rebuild();
      this._updateLegend();
    });

    document.getElementById('topbar-fullscreen').addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
      } else {
        document.exitFullscreen();
      }
    });
  }

  /* ── Keyboard ── */
  _bindKeyboard() {
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
      switch (e.key.toLowerCase()) {
        case 'w': document.getElementById('btn-wireframe').click(); break;
        case 'd': document.getElementById('btn-deformed').click(); break;
        case 'r': document.getElementById('btn-reset').click(); break;
        case 'c': document.getElementById('lb-screenshot').click(); break;
        case 'm': this._toggleMeasure(); break;
        case ' ': e.preventDefault(); document.getElementById('btn-play').click(); break;
        case 'arrowleft': this._setFrame(this.state.currentFrame - 1); break;
        case 'arrowright': this._setFrame(this.state.currentFrame + 1); break;
        case 'arrowup': case '1': this.viewer.setView('top'); break;
        case '2': this.viewer.setView('front'); break;
        case '3': this.viewer.setView('right'); break;
      }
    });
  }

  /* ── Click-to-pick / Probe ── */
  _bindProbe() {
    const vp = document.getElementById('viewport');
    vp.addEventListener('click', (e) => {
      // Skip if measure tool is active
      if (this.measure && this.measure.enabled) return;
      // Skip if clicking on UI elements
      if (e.target.closest('#toolbar') || e.target.closest('#anim-bar') || e.target.closest('#info') || e.target.closest('#legend') || e.target.closest('#sidebar')) return;

      const rect = this.viewer.renderer.domElement.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      const hit = this.viewer.pick(x, y);
      if (!hit) {
        document.getElementById('probe-info')?.classList.add('hidden');
        return;
      }

      if (this.state.data && this.state.currentField) {
        const fv = this.viewer.getFieldValueAtPoint(hit.point);
        const fieldKey = this.state.currentField.key || this.state.currentField.name || '';
        const fieldLabel = this.state.currentField.label || this.state.currentField.name || 'Field';
        const unit = this.state.currentField.unit || '';
        const range = this.viewer.getFieldRange();

        const probeEl = document.getElementById('probe-info');
        if (probeEl) {
          const val = fv !== null && fv.value !== undefined ? fv.value : 0;
          const valStr = typeof val === 'number' ? (Math.abs(val) < 0.001 ? val.toExponential(3) : val.toFixed(4)) : String(val);
          probeEl.querySelector('.probe-field').textContent = fieldLabel;
          probeEl.querySelector('.probe-value').textContent = valStr + (unit ? ' ' + unit : '');
          probeEl.querySelector('.probe-range').textContent = (range.min.toFixed(2)) + ' ~ ' + (range.max.toFixed(2));
          // Position near cursor
          const px = Math.min(e.clientX + 16, window.innerWidth - 200);
          const py = Math.min(e.clientY - 10, window.innerHeight - 80);
          probeEl.style.left = px + 'px';
          probeEl.style.top = py + 'px';
          probeEl.classList.remove('hidden');
        }
      }
    });
  }

  /* ── Measure Tool ── */
  _bindMeasureToggle() {
    // Toolbar button toggles measure mode
    document.getElementById('btn-measure').addEventListener('click', () => this._toggleMeasure());

    // Sidebar mode buttons
    const distBtn = document.getElementById('meas-mode-distance');
    const angleBtn = document.getElementById('meas-mode-angle');
    distBtn.addEventListener('click', () => {
      if (this.measure.enabled) {
        this.measure.disable();
        this.measure.enable('distance');
      }
      distBtn.classList.add('active');
      angleBtn.classList.remove('active');
    });
    angleBtn.addEventListener('click', () => {
      if (this.measure.enabled) {
        this.measure.disable();
        this.measure.enable('angle');
      }
      angleBtn.classList.add('active');
      distBtn.classList.remove('active');
    });

    // Clear button
    document.getElementById('meas-clear').addEventListener('click', () => {
      this.measure.clear();
      document.getElementById('measure-status').textContent = '测量已清除';
    });
  }

  _toggleMeasure() {
    const btn = document.getElementById('btn-measure');
    if (this.measure.enabled) {
      this.measure.disable();
      btn.classList.remove('active');
      this._toast('测量已关闭', 'info');
      document.getElementById('measure-status').textContent = '点击模型表面取点测量';
    } else {
      const mode = document.querySelector('#panel-measure .ctrl-btn.active')?.dataset.mode || 'distance';
      this.measure.enable(mode);
      btn.classList.add('active');
      this._toast('测量模式: ' + (mode === 'distance' ? '距离' : '角度') + ' — 点击模型表面取点', 'info');
      document.getElementById('measure-status').textContent = '测量已启用 — 点击表面取点';
    }
  }

  _rebuild() {
    if (!this.state.data) return;
    const opts = { frameIdx: this.state.currentFrame, field: this.state.currentField, colormap: this.state.colormapName };
    if (this.state.format === 'v2.0') {
      this.viewer.buildSceneFromVTP(this.state.data, opts);
    } else {
      this.viewer.buildScene(this.state.data, { ...opts, deformed: this.state.deformed, scaleFactor: this.state.scaleFactor });
    }
    this._updateLegend();
    this._updateAnimBar();
  }

  /* ── UI Updates ── */
  _updateAll(data) {
    this._updateTree(data);
    this._updateLegend();
    this._updateAnimBar();
    this._updateInfo(data);

    // Show overlays after data loaded
    document.getElementById('info').classList.remove('hidden');
    document.getElementById('legend').classList.remove('hidden');
  }

  _updateInfo(data) {
    const nodes = data.nodes || [];
    const elems = data.elements || {};
    const frames = data.frames || data.frame_files || [];
    let totalElems = 0;
    for (const arr of Object.values(elems)) totalElems += (arr || []).length;

    if (this.state.format === 'v2.0') {
      const stats = this.viewer.getVtpStats();
      document.getElementById('info-nodes').textContent = (stats.nodes || 0).toLocaleString();
      document.getElementById('info-elems').textContent = (stats.elements || 0).toLocaleString();
    } else {
      document.getElementById('info-nodes').textContent = Math.max(0, (nodes.length - 1)).toLocaleString();
      document.getElementById('info-elems').textContent = totalElems.toLocaleString();
    }
    document.getElementById('info-frames').textContent = frames.length.toLocaleString();
  }

  _updateTree(data) {
    const tree = document.getElementById('tree');
    tree.innerHTML = '';

    const addSection = (t) => {
      const el = document.createElement('div');
      el.className = 'tree-section';
      el.textContent = t;
      tree.appendChild(el);
    };
    const addItem = (icon, label, onClick, active) => {
      const el = document.createElement('div');
      el.className = 'tree-item' + (active ? ' active' : '');
      el.innerHTML = '<span style="width:14px;text-align:center;flex-shrink:0;font-size:11px">' + icon + '</span><span>' + label + '</span>';
      if (onClick) el.addEventListener('click', onClick);
      tree.appendChild(el);
      return el;
    };

    addSection('场变量');
    const fields = data.fields || [];
    if (fields.length === 0) {
      addItem('—', '无场变量');
    }
    for (const f of fields) {
      const active =
        this.state.currentField &&
        (this.state.currentField.key || this.state.currentField.name) === (f.key || f.name);
      addItem('▣', f.label || f.name || f.key || '未知', () => {
        this.state.currentField = f;
        this._rebuild();
      }, active);
    }

    addSection('模型');
    const nodes = data.nodes || [];
    const elems = data.elements || {};
    let totalElems = 0;
    for (const arr of Object.values(elems)) totalElems += (arr || []).length;

    if (this.state.format === 'v2.0') {
      const stats = this.viewer.getVtpStats();
      addItem('◈', '节点: ' + (stats.nodes || 0).toLocaleString());
    } else {
      addItem('◈', '节点: ' + Math.max(0, (nodes.length - 1)).toLocaleString());
    }
    addItem('◇', '单元: ' + totalElems.toLocaleString());

    const etList = Object.keys(elems);
    if (etList.length > 0) {
      const badge = document.createElement('div');
      badge.className = 'tree-item';
      badge.innerHTML = '<span style="width:14px;text-align:center;flex-shrink:0;font-size:11px">📦</span><span><span class="tree-badge ' + (this.state.format === 'v2.0' ? 'green' : 'yellow') + '">' + (this.state.format === 'v2.0' ? 'VTP 轻量' : 'JSON 兼容') + '</span></span>';
      tree.appendChild(badge);
    }
    for (const et of etList) {
      addItem('—', et + ': ' + (elems[et] || []).length.toLocaleString());
    }

    addSection('分析步');
    const steps = data.steps || [];
    if (steps.length === 0) addItem('—', '无');
    for (const s of steps) {
      addItem('▸', s.label || s.name || 'Step');
    }

    addSection('信息');
    if (data.model_name) addItem('📄', data.model_name);
    if (data.job_name) addItem('⚙', data.job_name);
    if (data.deformation_scale_factor) addItem('📏', '变形比例: ' + data.deformation_scale_factor + 'x');
    if (data.abaqus_version) addItem('🔧', 'Abaqus ' + data.abaqus_version);
    if (data.export_time) addItem('🕐', data.export_time);
  }

  _updateLegend() {
    const title = document.getElementById('legend-title');
    const bar = document.getElementById('legend-bar');
    const minL = document.getElementById('legend-min');
    const maxL = document.getElementById('legend-max');

    if (!this.state.currentField || !this.state.data) {
      title.textContent = '未选择场变量';
      bar.style.background = 'var(--bg-elevated)';
      minL.textContent = '0';
      maxL.textContent = '0';
      return;
    }

    let fmin = 0, fmax = 1;
    const fieldKey = this.state.currentField.key || this.state.currentField.name;
    if (this.state.format === 'v2.0' && this.viewer._lastVtpResult && this.viewer._lastVtpResult.fieldValues) {
      const valid = this.viewer._lastVtpResult.fieldValues.filter((v) => v != null && !isNaN(v));
      if (valid.length > 0) { fmin = Math.min(...valid); fmax = Math.max(...valid); }
    } else if (this.state.data) {
      const frame = (this.state.data.frames || [])[this.state.currentFrame];
      if (frame && frame[fieldKey]) {
        fmin = frame[fieldKey].min !== undefined ? frame[fieldKey].min : 0;
        fmax = frame[fieldKey].max !== undefined ? frame[fieldKey].max : 1;
      }
    }

    const unit = this.state.currentField.unit || '';
    const label = this.state.currentField.label || this.state.currentField.name || 'Field';
    title.textContent = label + (unit ? ' (' + unit + ')' : '');
    bar.style.background = colormapToCSS(this.state.colormapName);

    const fmt = (v) => {
      if (v == null) return '0';
      if (Math.abs(v) < 0.001 || Math.abs(v) > 1e6) return v.toExponential(2);
      return parseFloat(v.toPrecision(4)).toString();
    };
    minL.textContent = fmt(fmin);
    maxL.textContent = fmt(fmax);
  }

  _updateAnimBar() {
    const bar = document.getElementById('anim-bar');
    if (!this.state.data) { bar.classList.add('hidden'); return; }
    const frames = this.state.data.frames || this.state.data.frame_files || [];
    if (frames.length <= 1) { bar.classList.add('hidden'); return; }
    bar.classList.remove('hidden');

    const slider = document.getElementById('frame-slider');
    slider.max = frames.length - 1;
    slider.value = this.state.currentFrame;
    document.getElementById('frame-label').textContent = (this.state.currentFrame + 1) + ' / ' + frames.length;

    if (this.state.format === 'v1.0') {
      const frame = frames[this.state.currentFrame];
      if (frame && frame.time !== undefined) {
        document.getElementById('ab-time').textContent = 't=' + parseFloat(frame.time.toPrecision(4));
        return;
      }
    }
    document.getElementById('ab-time').textContent = '';
  }

  _setFileBadge(name) {
    const badge = document.getElementById('file-badge');
    badge.textContent = name;
    badge.classList.add('visible');
    document.getElementById('status-dot').classList.add('loaded');
  }

  _updateStatus(msg) {
    const dot = document.getElementById('status-dot');
    if (msg.includes('失败') || msg.includes('失败')) dot.style.background = 'var(--accent-red)';
    else dot.style.background = 'var(--accent-green)';
  }

  /* ── Toast ── */
  _toast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('out');
      setTimeout(() => el.remove(), 300);
    }, 3000);
  }
}


