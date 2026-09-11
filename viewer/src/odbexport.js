/**
 * ODB Export Client.
 * Handles the export API calls to the Python server.
 */

export class ODBExportClient {
  constructor(viewer, state, ui) {
    this.viewer = viewer;
    this.state = state;
    this.ui = ui;
  }

  init() {
    const btn = document.getElementById('export-btn');
    const pathInput = document.getElementById('odb-path');

    btn.addEventListener('click', () => this.exportFromOdb());
    pathInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.exportFromOdb();
    });

    document.getElementById('load-exported-btn').addEventListener('click', () => this._loadExportedJson());
  }

  async exportFromOdb() {
    const odbPath = document.getElementById('odb-path').value.trim();
    const statusEl = document.getElementById('export-status');
    const btn = document.getElementById('export-btn');
    const loadArea = document.getElementById('load-exported');

    if (!odbPath) {
      statusEl.textContent = '请填写 ODB 文件路径';
      statusEl.className = 'error';
      return;
    }

    btn.disabled = true;
    statusEl.textContent = '正在从 ODB 导出... (可能需要较长时间)';
    statusEl.className = '';
    loadArea.style.display = 'none';

    try {
      const resp = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          odb_path: odbPath,
          step_index: -1,
          frame_step: 1,
          deformation_scale: 1.0,
          format_version: document.getElementById('export-format').value,
        }),
      });
      const result = await resp.json();
      if (result.ok) {
        statusEl.textContent = '导出完成: ' + (result.node_count || 0).toLocaleString() + ' 节点, ' + (result.elem_count || 0).toLocaleString() + ' 单元, ' + (result.frame_count || 0) + ' 帧';
        statusEl.className = 'success';
        this.state.exportedJsonPath = result.output_path;
        loadArea.style.display = 'block';
        await this._loadExportedJson(result.output_path);
      } else {
        statusEl.textContent = '导出失败: ' + (result.error || '未知错误');
        statusEl.className = 'error';
      }
    } catch (err) {
      statusEl.textContent = '导出错误: ' + err.message;
      statusEl.className = 'error';
    } finally {
      btn.disabled = false;
    }
  }

  async _loadExportedJson(path) {
    const p = path || this.state.exportedJsonPath;
    if (!p) return;
    const fname = p.split(/[\\/]/).pop();
    try {
      const resp = await fetch('/' + fname);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      this.state.data = data;
      const fmt = data.format_version || 'v1.0';
      this.state.format = (fmt === '2.0' || fmt.startsWith('2.')) ? 'v2.0' : 'v1.0';
      this.state.currentFrame = 0;
      this.state.currentField = (data.fields || [])[0] || null;
      const opts = { frameIdx: 0, field: this.state.currentField, colormap: this.state.colormapName };
      if (this.state.format === 'v2.0') {
        await this.viewer.buildSceneFromVTP(data, opts);
      } else {
        this.viewer.buildScene(data, { ...opts, deformed: this.state.deformed, scaleFactor: this.state.scaleFactor });
      }
      const updateAll = this.ui._updateAll || this.ui.updateAll;
      if (updateAll) updateAll.call(this.ui, data);
    } catch (err) {
      console.error('Load exported failed:', err);
    }
  }
}
