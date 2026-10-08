/**
 * ODB Export Client.
 * Handles the export API calls to the Python server.
 */

export function resultSelection(data, search) {
  const params = new URLSearchParams(search);
  const frames = data.frames || [];
  const requestedFrame = params.get('frame');
  const isStatic = (data.steps || []).some(s => /STATIC/i.test(s.procedure || ''));
  const frameIdx = requestedFrame === 'last' || (requestedFrame === null && isStatic) ? frames.length - 1 :
    requestedFrame === null ? 0 : Number(requestedFrame);
  if (!Number.isInteger(frameIdx) || frameIdx < 0 || frameIdx >= frames.length) {
    throw new Error('指定结果帧不存在');
  }
  const fields = data.fields || [];
  const requestedField = params.get('field');
  const field = requestedField === null ? fields.find(f => f.name === 'S_mises') || fields[0] || null : fields.find(f => f.name === requestedField);
  if (requestedField !== null && !field) throw new Error('指定场变量不存在：' + requestedField);
  return {frameIdx, field};
}

export class ODBExportClient {
  constructor(viewer, state, ui) {
    this.viewer = viewer;
    this.state = state;
    this.ui = ui;
    this.sessionReady = this._connectSession().catch(error => { this.sessionError = error; });
    this.request = null;
  }

  init() {
    const btn = document.getElementById('export-btn');
    const pathInput = document.getElementById('odb-path');

    btn.addEventListener('click', () => this.exportFromOdb());
    pathInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.exportFromOdb();
    });

    const cancel = document.createElement('button');
    cancel.textContent = '取消导出';
    cancel.addEventListener('click', async () => {
      if (this.state.exportTaskId) await fetch('/api/cancel/' + this.state.exportTaskId, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
      });
    });
    btn.after(cancel);
    document.getElementById('load-exported-btn').addEventListener('click', () => this._loadExportedJson());
    const historyArea = document.createElement('details');
    historyArea.id = 'task-history';
    const title = document.createElement('summary');
    title.textContent = '结果任务历史';
    const refresh = document.createElement('button');
    refresh.textContent = '刷新历史';
    const list = document.createElement('div');
    const diagnostics = document.createElement('pre');
    diagnostics.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:240px;overflow:auto';
    const render = async () => {
      try {
        await this.sessionReady;
        const response = await fetch('/api/tasks');
        if (!response.ok) throw new Error('无法读取任务历史，请使用本次服务的完整链接');
        const payload = await response.json();
        list.replaceChildren();
        for (const task of payload.tasks) {
          const row = document.createElement('div');
          row.style.cssText = 'padding:8px 0;overflow-wrap:anywhere;border-bottom:1px solid #30363d';
          const label = document.createElement('div');
          const status = {completed:'已完成',failed:'失败',interrupted:'已中断',cancelled:'已取消',queued:'排队中',running:'导出中',cancelling:'正在取消'};
          label.textContent = `${new Date(task.created_at * 1000).toLocaleString()} · ${status[task.status] || task.status}\n${task.params.odb_path}`;
          row.append(label);
          const action = document.createElement('button');
          action.textContent = task.status === 'completed' ? '打开结果' : '查看日志';
          action.addEventListener('click', async () => {
            try {
              if (task.status === 'completed') await this.loadTaskResult(task);
              else {
                const r = await fetch('/api/diagnostics/' + task.task_id);
                if (!r.ok) throw new Error('无法读取日志');
                const d = await r.json();
                diagnostics.textContent = [d.task.error || '', d.next_action, d.log_tail].join('\n');
              }
            } catch (error) { diagnostics.textContent = error.message; }
          });
          row.append(action);
          list.append(row);
        }
        if (!payload.tasks.length) list.textContent = '暂无导出任务';
      } catch (error) { diagnostics.textContent = error.message; }
    };
    refresh.addEventListener('click', render);
    historyArea.addEventListener('toggle', () => {if (historyArea.open) render();});
    historyArea.append(title, refresh, list, diagnostics);
    document.getElementById('export-status').after(historyArea);
  }

  async _connectSession() {
    const token = new URLSearchParams(location.hash.slice(1)).get('token');
    if (!token) return;
    const response = await fetch('/api/session', {
      method: 'POST', headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }, body: '{}'
    });
    if (!response.ok) throw new Error('会话认证失败，请使用服务启动时的链接');
    history.replaceState(null, '', location.pathname + location.search);
  }

  async loadStartupResult() {
    const taskId = new URLSearchParams(location.search).get('task');
    if (taskId === null) return; // An ordinary viewer URL must stay empty.
    const welcome = document.getElementById('welcome-status');
    try {
      if (!/^[0-9a-f]{32}$/.test(taskId)) throw new Error('结果链接无效');
      welcome.textContent = '正在加载指定计算结果…';
      await this.sessionReady;
      if (this.sessionError) throw this.sessionError;
      const response = await fetch('/api/tasks/' + taskId);
      if (!response.ok) throw new Error('无法读取指定结果，请使用完整的结果链接');
      const result = await response.json();
      if (result.task_id !== taskId) throw new Error('结果与链接不匹配');
      if (result.status !== 'completed') throw new Error('该结果尚不可用：' + result.status);
      if (result.output_url !== '/exports/' + taskId + '/model.json') throw new Error('结果地址不匹配');
      await this.loadTaskResult(result, location.search);
    } catch (error) {
      welcome.textContent = '结果加载失败：' + error.message;
      document.getElementById('welcome').classList.remove('hidden');
      this.ui._updateStatus(welcome.textContent);
    }
  }

  async loadTaskResult(result, search = '') {
    await this._loadExportedJson(result.output_url, search);
    this.state.exportedJsonPath = result.output_url;
    this.state.exportTaskId = result.task_id;
    const source = result.params.odb_path;
    document.getElementById('odb-path').value = source;
    document.getElementById('export-section').value = result.params.section_point || '';
    document.getElementById('export-units').value = result.params.unit_system || '';
    this.ui._setFileBadge(source);
    this.ui._updateStatus('已加载: ' + source);
    const url = new URL(location.href);
    url.searchParams.set('task', result.task_id);
    url.searchParams.delete('field');
    url.searchParams.delete('frame');
    if (this.state.currentField) url.searchParams.set('field', this.state.currentField.name);
    if (Number.isInteger(this.state.currentFrame)) url.searchParams.set('frame', this.state.currentFrame);
    url.hash = '';
    history.replaceState(null, '', url.pathname + url.search);
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
    this.ui.resetResult?.();
    statusEl.textContent = '正在从 ODB 导出... (可能需要较长时间)';
    statusEl.className = '';
    loadArea.style.display = 'none';

    try {
      await this.sessionReady;
      if (this.sessionError) throw this.sessionError;
      const selection = odbPath + '|' + document.getElementById('export-section').value + '|' + document.getElementById('export-units').value;
      if (!this.request || this.request.path !== selection) {
        this.request = {path: selection, id: crypto.randomUUID()};
      }
      const resp = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          odb_path: odbPath,
          request_id: this.request.id,
          step_index: -1,
          frame_step: 1,
          deformation_scale: 1.0,
          unit_system: document.getElementById('export-units').value,
          ...(document.getElementById('export-section').value ? {section_point: Number(document.getElementById('export-section').value)} : {}),
        }),
      });
      let result = await resp.json();
      if (!resp.ok) throw new Error(result.error || '导出请求失败');
      this.state.exportTaskId = result.task_id;
      while (['queued', 'running', 'cancelling'].includes(result.status)) {
        statusEl.textContent = '导出任务 ' + result.task_id.slice(0, 8) + ': ' + result.status;
        await new Promise(resolve => setTimeout(resolve, 750));
        const status = await fetch('/api/tasks/' + result.task_id);
        if (!status.ok) throw new Error('无法查询导出任务；重新点击将查询同一请求');
        result = await status.json();
      }
      if (result.status !== 'completed') {
        this.request = null;
        throw new Error(result.error || result.status);
      }
      await this.loadTaskResult(result);
      statusEl.textContent = '已加载: ' + odbPath + ' · ' + result.node_count + ' 节点 · ' + result.frame_count + ' 帧';
      statusEl.className = 'success';
      loadArea.style.display = 'block';
      this.request = null;
    } catch (err) {
      statusEl.textContent = '导出错误: ' + err.message;
      statusEl.className = 'error';
    } finally {
      btn.disabled = false;
    }
  }

  async _loadExportedJson(path, search = location.search) {
    const p = path || this.state.exportedJsonPath;
    if (!p) return;
    if (!p.startsWith('/exports/')) throw new Error('Invalid export URL');
    this.ui.resetResult?.();
    try {
      const epoch = this.ui._resultEpoch;
      const resp = await fetch(p);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if (epoch !== this.ui._resultEpoch) throw new Error('已切换到其他结果，本次加载已取消');
      data._baseUrl = p;
      this.viewer._fileCache = null;
      this.state.data = data;
      const fmt = String(data.format_version || 'v1.0');
      this.state.format = (fmt === '2.0' || fmt.startsWith('2.') || fmt === '3.0' || fmt.startsWith('3.')) ? 'v3.0' : 'v1.0';
      const selection = resultSelection(data, search);
      this.state.currentFrame = selection.frameIdx;
      this.state.currentField = selection.field;
      const opts = { ...selection, colormap: this.state.colormapName };
      if (this.state.format === 'v3.0') {
        await this.viewer.buildSceneFromVTU(data, opts);
      } else {
        this.viewer.buildScene(data, { ...opts, deformed: this.state.deformed, scaleFactor: this.state.scaleFactor });
      }
      if (epoch !== this.ui._resultEpoch) throw new Error('已切换到其他结果，本次加载已取消');
      const updateAll = this.ui._updateAll || this.ui.updateAll;
      if (updateAll) updateAll.call(this.ui, data);
    } catch (err) {
      console.error('Load exported failed:', err);
      throw err;
    }
  }
}

