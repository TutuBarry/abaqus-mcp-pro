/**
 * Progress loader utility for showing load progress.
 */

export class ProgressLoader {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = containerId || 'progress-overlay';
      document.body.appendChild(this.container);
    }
    this.container.innerHTML =`
      <div class="progress-inner">
        <div class="progress-spinner"></div>
        <div class="progress-text" id="progress-text">Loading...</div>
        <div class="progress-track">
          <div class="progress-bar" id="progress-bar"></div>
        </div>
      </div>
    `;
    this.bar = document.getElementById('progress-bar');
    this.text = document.getElementById('progress-text');
    this.hide();
  }

  show(msg = 'Loading...') {
    this.text.textContent = msg;
    this.container.style.display = 'flex';
    this.bar.style.width = '0%';
  }

  update(percent, msg) {
    this.bar.style.width = Math.min(100, Math.max(0, percent)) + '%';
    if (msg) this.text.textContent = msg;
  }

  hide() {
    this.container.style.display = 'none';
  }

  dispose() {
    if (this.container.parentNode) {
      this.container.parentNode.removeChild(this.container);
    }
  }
}
