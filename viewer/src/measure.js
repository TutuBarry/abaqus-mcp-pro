/**
 * Measurement tool for 3D viewer.
 * Supports: distance, angle, and annotation.
 */

import * as THREE from 'three';

export class MeasureTool {
  constructor(viewer) {
    this.viewer = viewer;
    this.enabled = false;
    this.points = [];
    this.markers = [];
    this.lines = [];
    this.labels = [];
    this.mode = 'distance'; // 'distance' | 'angle'
    this._activeLine = null;
    this._clickHandler = null;
  }

  enable(mode = 'distance') {
    this.mode = mode;
    this.enabled = true;
    this.points = [];
    this.viewer.container.style.cursor = 'crosshair';
    this._clickHandler = (e) => this._onClick(e);
    this.viewer.renderer.domElement.addEventListener('click', this._clickHandler);
  }

  disable() {
    this.enabled = false;
    this.viewer.container.style.cursor = 'default';
    if (this._clickHandler) {
      this.viewer.renderer.domElement.removeEventListener('click', this._clickHandler);
      this._clickHandler = null;
    }
    this.clear();
  }

  clear() {
    this.points = [];
    this.markers.forEach(m => { this.viewer.scene.remove(m); });
    this.lines.forEach(l => { this.viewer.scene.remove(l); });
    this.labels.forEach(l => { if (l.parentNode) l.parentNode.removeChild(l); });
    this.markers = [];
    this.lines = [];
    this.labels = [];
    if (this._activeLine) {
      this.viewer.scene.remove(this._activeLine);
      this._activeLine = null;
    }
  }

  _onClick(e) {
    if (!this.enabled) return;
    const rect = this.viewer.renderer.domElement.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(new THREE.Vector2(x, y), this.viewer.camera);

    const meshes = [];
    this.viewer.meshGroup.children.forEach(c => {
      if (c.isMesh) meshes.push(c);
    });

    const hits = raycaster.intersectObjects(meshes);
    if (hits.length === 0) return;

    const point = hits[0].point.clone();

    if (this.mode === 'distance') {
      this.points.push(point);
      this._addMarker(point);
      if (this.points.length === 2) {
        this._drawDistance(this.points[0], this.points[1]);
        this.points = [];
      }
    } else if (this.mode === 'angle') {
      this.points.push(point);
      this._addMarker(point);
      if (this.points.length === 3) {
        this._drawAngle(this.points[0], this.points[1], this.points[2]);
        this.points = [];
      }
    }
  }

  _addMarker(point) {
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.03, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xff4444, depthTest: true })
    );
    sphere.position.copy(point);
    this.viewer.scene.add(sphere);
    this.markers.push(sphere);
  }

  _drawDistance(p1, p2) {
    const dist = p1.distanceTo(p2);
    const mid = p1.clone().add(p2).multiplyScalar(0.5);

    const points = [p1, p2];
    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: 0xffaa00, linewidth: 2, depthTest: true });
    const line = new THREE.Line(geom, mat);
    this.viewer.scene.add(line);
    this.lines.push(line);

    // Add arrow heads
    this._addArrow(p1, p2);
    this._addArrow(p2, p1);

    // Label
    const div = document.createElement('div');
    div.className = 'measure-label';
    div.textContent = dist < 1 ? `${(dist * 1000).toFixed(1)} mm` : `${dist.toFixed(3)} m`;
    div.style.cssText = 'position:absolute;color:#ffaa00;font-size:11px;font-weight:600;font-family:var(--font-mono);background:rgba(0,0,0,0.75);padding:2px 6px;border-radius:3px;pointer-events:none;white-space:nowrap;z-index:100;';
    this._updateLabelPos(div, mid);
    document.getElementById('viewport').appendChild(div);
    this.labels.push(div);
  }

  _addArrow(from, to) {
    const dir = new THREE.Vector3().copy(to).sub(from);
    const len = dir.length();
    if (len < 0.001) return;
    dir.normalize();
    const arrowSize = Math.min(len * 0.08, 0.05);
    const mid = from.clone().add(to).multiplyScalar(0.5);
    // Don't draw at mid, draw at the end
    const start = to.clone().add(dir.clone().multiplyScalar(-arrowSize * 2));
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(arrowSize * 0.6, arrowSize * 1.5, 6),
      new THREE.MeshBasicMaterial({ color: 0xffaa00, depthTest: true })
    );
    cone.position.copy(start);
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    this.viewer.scene.add(cone);
    this.lines.push(cone);
  }

  _drawAngle(p1, p2, p3) {
    const v1 = new THREE.Vector3().copy(p1).sub(p2);
    const v2 = new THREE.Vector3().copy(p3).sub(p2);
    const angle = v1.angleTo(v2) * 180 / Math.PI;

    // Draw arc
    const r = Math.min(v1.length(), v2.length()) * 0.3;
    v1.normalize();
    v2.normalize();
    const arcPts = [];
    const steps = 20;
    const startAngle = Math.atan2(v1.x, v1.z);
    const endAngle = Math.atan2(v2.x, v2.z);
    let a1 = startAngle, a2 = endAngle;
    if (a2 < a1) a2 += Math.PI * 2;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const a = a1 + (a2 - a1) * t;
      const x = p2.x + r * Math.sin(a);
      const z = p2.z + r * Math.cos(a);
      arcPts.push(new THREE.Vector3(x, p2.y, z));
    }

    const geom = new THREE.BufferGeometry().setFromPoints(arcPts);
    const mat = new THREE.LineBasicMaterial({ color: 0x44aaff, depthTest: true });
    const arc = new THREE.Line(geom, mat);
    this.viewer.scene.add(arc);
    this.lines.push(arc);

    // Label
    const midAngle = (a1 + a2) / 2;
    const labelPos = new THREE.Vector3(
      p2.x + r * 0.7 * Math.sin(midAngle),
      p2.y + r * 0.7,
      p2.z + r * 0.7 * Math.cos(midAngle)
    );
    const div = document.createElement('div');
    div.textContent = `${angle.toFixed(1)}°`;
    div.style.cssText = 'position:absolute;color:#44aaff;font-size:12px;font-weight:600;font-family:var(--font-mono);background:rgba(0,0,0,0.75);padding:2px 6px;border-radius:3px;pointer-events:none;white-space:nowrap;z-index:100;';
    this._updateLabelPos(div, labelPos);
    document.getElementById('viewport').appendChild(div);
    this.labels.push(div);
  }

  _updateLabelPos(el, worldPos) {
    const update = () => {
      const vec = worldPos.clone().project(this.viewer.camera);
      const rect = this.viewer.renderer.domElement.getBoundingClientRect();
      const x = (vec.x * 0.5 + 0.5) * rect.width;
      const y = (-vec.y * 0.5 + 0.5) * rect.height;
      el.style.left = x + 'px';
      el.style.top = y + 'px';
    };
    update();
    // Re-position on next frame
    requestAnimationFrame(update);
  }
}

