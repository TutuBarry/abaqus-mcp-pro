# Changelog

All notable changes to Abaqus MCP Pro will be documented in this file.

## [1.0.0] - 2026-09-02

### Added
- Initial release of Abaqus MCP Pro
- TCP socket bridge with 10-50ms latency (vs 100-200ms for file-based IPC)
- 22 MCP tools for full Abaqus automation: model query, job management, ODB inspection, KPI extraction, capsule tracking, physics contracts, report generation, viewport capture
- 13 MCP prompts for guided workflows: static, dynamic, modal, thermal, contact, fatigue, coupled, optimization, material, mesh, ODB extraction, job debugging
- 74 MCP resources: session telemetry, skills knowledge base, CAE-Agent-Hub integration
- AST error diagnostics: auto-analyzes KeyError, AttributeError, NameError, TypeError
- 3 CLI tools: check, doctor, setup
- Dual transport: TCP socket (primary) + file IPC (fallback)
- noGUI mode for batch execution
- Skills knowledge base with 20+ skill definitions
- Capsule experiment state tracking with diff capability
- Physics contracts validation engine
- Convergence advisor for solver troubleshooting
- Silent failure detection for common Abaqus pitfalls
- Automatic simulation report generation
- Viewport capture and multi-viewport support
- Extended tool set: 50+ additional Abaqus operations (forces, moments, BCs, constraints, surfaces, contact, explicit steps, thermal steps)

[1.0.0]: https://github.com/TutuBarry/abaqus-mcp-pro/releases/tag/v1.0.0
