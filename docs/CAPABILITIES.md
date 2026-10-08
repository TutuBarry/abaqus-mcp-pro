# Runtime capabilities and migration

The MCP surface has 138 tools, 13 prompts and 74 resources. Registration is not proof that all business operations have been validated in Abaqus. A generated schema snapshot is in `reference/tool-manifest.json`.

Current release candidate: **1.1.0rc2**. Actual CAE 2026 menu start/stop, GUI job submission/monitoring and ODB lifecycle passed. Browser visual/GPU and other Abaqus versions remain unverified. See [rc2 delivery](DELIVERY_RC2_2026-09-30.md); dated evidence sections below are historical.

## Bridge

`bridge_capabilities` reports the actual runtime methods, protocol version and read-only policy. The installed GUI plugin now includes a sibling `abaqus_mcp_pro_runtime` directory; reinstall using `abaqus-mcp-pro-setup` after upgrading, then restart the bridge in CAE. Copying only the GUI plugin file is insufficient.

Set the same `ABAQUS_MCP_TOKEN` in the MCP client process and Abaqus process. This protects socket and file commands when configured. Bindings default to loopback. `ABAQUS_MCP_READ_ONLY=1` disables arbitrary kernel execution and write-mode ODB opening; wrappers implemented through arbitrary code are consequently unavailable even when their MCP annotation says read-only. Annotations describe intended behavior and are not enforcement.

Kernel access is serialized, including reads. `run_python` returns an operation_id and includes it in failure messages. Supply a stable ID to retry the same operation. After a timeout query `bridge_request_status` before resubmitting a mutation. The cache retains at most128 operations in the current bridge process. Unknown status after restart/eviction does not mean the mutation never happened. GUI main-thread work can delay status requests; running arbitrary code cannot safely be cancelled.

`submit_job` now defaults to `wait=False`; use `monitor_job_status` to inspect completion. `wait=True` blocks the kernel; an aborted/terminated job raises an error. `create_capsule` now requires an explicit job_name when multiple jobs exist and rejects incomplete capture instead of silently storing partial results.

## Viewer

Use `abaqus-mcp-pro-viewer` after wheel installation, or `python viewer/serve_viewer.py` from a built source checkout. Open the URL printed at startup; its token is exchanged for an HttpOnly SameSite cookie and removed from the URL fragment. HTTP is intended for local use.

Environment controls: `ABAQUS_VIEWER_HOST` (127.0.0.1), `ABAQUS_VIEWER_PORT` (8080), `ABAQUS_VIEWER_TOKEN`, `ABAQUS_VIEWER_ODB_ROOT` (optional input boundary), `ABAQUS_VIEWER_EXPORT_ROOT` (default ~/.abaqus-mcp-pro/exports), and `ABAQUS_COMMAND` (executable/batch path). Output files persist for inspection; remove obsolete runs manually only after checking whether they are still needed.

Exports use POST `/api/export` with typed data and request_id, GET `/api/tasks/{id}`, and POST `/api/cancel/{id}`. Completed results have `/exports/{id}/model.json` URLs and matching VTU frames. No fallback to demo data occurs for export paths. The UI exports VTU; legacy JSON files can still be opened through file loading. Section point selection is available for shell/beam output.

GET `/api/tasks` lists the latest 100 persisted tasks. GET `/api/diagnostics/{id}` provides status and a bounded export-log tail. Both require the same authentication as exports. Parsed frames use a four-entry LRU with a 96 MiB estimated retained-data budget; transient XML, scene and GPU memory are additional. Mesh buffers are reused when topology matches.

`list_project_runs` and `compare_project_runs` provide local history and JSON/CSV/HTML KPI reports. The equivalent CLI is `abaqus-mcp-pro-project history|compare`. Declared units must match and different selectors do not share baselines.

Missing field values are NaN with missing counts, excluded from finite ranges and shown in grey. An unsupported element or invalid selector is an error. High-order rendering uses corner linearization. The exported averaging metadata must be considered when comparing contours with Abaqus/CAE; the viewer is not a substitute for a native engineering acceptance query.

## Reproducible domain workflow

`abaqus-mcp-pro-verify` prepares the bundled structural static/contact suite. Add `--run` to execute the configured solver. Provide a custom JSON manifest for parameter studies and acceptance contracts. See [reference package](../examples/verification/README.md) and [delivery evidence](DELIVERY_2026-09-26.md).

## Abaqus 2026 evidence update (2026-09-28)

The six reference cases and three load points passed in Abaqus 2026. Kernel modeling and socket requests were verified in CAE noGUI; interactive GUI menus are still pending. See [real validation](ABAQUS_2026_VALIDATION.md). Model snapshots explicitly list unavailable repositories. Abaqus launcher errors are failures even with process exit code0. Command detection now includes Program Files installations when the current process has a stale PATH.
