# Changelog

## 1.1.0rc2 — 2026-09-30 (local candidate)

- Cache parsed frames with bounded LRU, cancel obsolete reads and prefetch one adjacent frame. Reuse surface and line geometry buffers; preserve the visible frame while loading.
- Add authenticated viewer task history and bounded diagnostic log tails.
- Add `list_project_runs`, `compare_project_runs`, and `abaqus-mcp-pro-project`; export comparable KPI reports as JSON, CSV and HTML with selectors and provenance.
- Add reproducible friction/sliding and plastic contact examples, projected contact-area estimates, pressure profiles and independently reported convergence metrics.
- Verify real CAE 2026 menu start/stop, job submission/monitoring and ODB lifecycle. Preserve and disable recognizable legacy duplicate plugins during installation.
- Upgrade Vite to 7.3.6; source builds require Node 20.19+ or 22.12+. Add Windows to the configured Python CI matrix; remote execution remains pending.

See [delivery evidence and limitations](docs/DELIVERY_RC2_2026-09-30.md). Browser visual/GPU, cross-version Abaqus, and the timed-out large solid-contact case are not marked passed.

## 1.1.0rc1 — 2026-09-30

Contact-pair outputs, automatic completed-result links, unit declarations and viewer result isolation. See [rc1 evidence](docs/DELIVERY_2026-09-30.md).
