# Delivery plan and verification log

Baseline: 2026-09-26, commit74d5d7d plus the existing server/tools/startup-test changes. Existing local edits are preserved.

## Current iteration: 1.1.0rc2 (2026-09-30)

See [rc2 delivery](docs/DELIVERY_RC2_2026-09-30.md). Source implementation completed for parsed-frame LRU/prefetch/cancellation, mesh buffer reuse, authenticated task history/diagnostics, project MCP/CLI comparisons, and friction/plastic contact examples. 391 Python / 43 frontend tests pass.

Actual CAE menu start/stop, GUI solver submission/monitoring and ODB open/summary/close passed. Browser visual/GPU acceptance remains blocked by browser URL policy recognition. Cross-version Abaqus and remote CI remain unverified. Contact convergence is now measured separately for force, projected-area estimate and peaks; failed metrics remain visible. Local release validation is tracked in VALIDATION_RC2_2026-09-30.json.

Real T3D2 rod scaling passed through 1,000,001 nodes (U-only, two frames); CPU parse/buffer updates measured separately from GPU. The 124,138-node solid contact run timed out at 600 s and remains unaccepted. See the rc2 report for measured limits.

## Historical rc1 iteration: 2026-09-30

Version 1.1.0rc1. See [delivery report](docs/DELIVERY_2026-09-30.md) for current evidence; earlier counts below are historical.

| Priority | Delivered implementation / evidence | Remaining acceptance |
|---|---|---|
| P0 viewer | Empty startup, exact result links, static final-frame/Mises defaults, corrected legend, source/declared units, result cleanup, late-response rejection, playback backpressure | Browser visual and interactive end-to-end inspection blocked by unavailable browser connection |
| P0 workflow | Completed local jobs export automatically; new open_result_viewer tool; workflow --viewer; content-based identity; export errors separate from solver success | GUI submit path requires actual CAE menu/event-loop inspection; noGUI path passed real end-to-end |
| P1 contact | Contact pair fields, missing-data NaN, connected mesh bodies, contact-output surface filter; 156 frame/field native ODB comparisons passed | Compare actual CAE and browser screenshots; clipping is a display clip, not a generated cut-surface mesh |
| P1 credibility | Flat and curved contact at three mesh levels; equilibrium, energy and contact checks; reaction changes 0.58% and 1.71% | Peak stress/pressure and general engineering accuracy are not certified by reaction convergence |
| P2 performance | Real exports at 2,428 / 7,433 / 16,758 nodes; CPU geometry benchmark to 800,000 synthetic nodes; bounded frame-text cache | Browser GPU/FPS/peak memory and million-node end-to-end case remain unmeasured |
| P2 release | Updated schemas, documentation and local candidate package validation | Remote CI, cross-version Abaqus checks and public release not performed |

| Workstream | Status | Evidence / remaining gate |
|---|---|---|
| Audit regression fixtures | Software complete | Executable data, protocol, generated-code, lifecycle and HTTP tests |
| Viewer input and export identity | Software complete | Typed JSON, authenticated local service, export-specific routes |
| ODB/KPI and topology correctness | Abaqus 2026 reference checks passed | Multi-instance/nonzero/missing fixtures, scalar API, cell topology and section-point tests |
| Transport and execution contract | noGUI kernel/socket verified; GUI event loop pending | Shared dispatch/authentication, serialization, operation IDs, capabilities |
| Materials, capsules, installation | Software complete | Correct table shapes, unambiguous jobs, file hashes, packaged runtime/resources |
| Real Abaqus benchmarks | Six cases passed on Abaqus 2026 | 2026-09-28 real solver, raw ODB comparison and VTU validation; other versions pending |
| Lifecycle and performance | Software complete within documented scope | Export queue/status/cancel/restart; bounded array reduction; million-node solver/render benchmark pending |
| Release documentation and CI | Local complete; remote CI not run | Capability matrix, smoke checks, validation report and revised CI |
| Initial domain workflow | Six cases and three load points passed | Static/contact reference suite, load scan, portable replay, numeric report |

## Verification policy

No fixture is reported as a real solver result. Preparation, missing solver, failed extraction and failed numerical contracts never imply PASS. Full engineering acceptance still requires licensed Abaqus and the matrix documented in examples/verification/README.md.

## Results

- Python tests:379 passed; frontend:15 passed; Python statement coverage last measured on 2026-09-26:42.25%.
- Browser: sample rendering and frame navigation inspected; no console errors at inspection.
- See docs/DELIVERY_2026-09-26.md for the scope, limitations, rescore and future direction.
- See docs/VALIDATION.json for final packaging and environment results.

## 2026-09-28 real environment validation

See docs/ABAQUS_2026_VALIDATION.md and docs/VALIDATION_2026-09-28.json. Abaqus 2026 is now installed and the initial solver gate has passed. GUI interaction, cross-version support, mesh convergence and large-model benchmarks remain pending.
