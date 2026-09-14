
# Contributing to Abaqus MCP Pro

Thanks for your interest in contributing! This document covers development setup,
code style, testing, and the pull request process.

---

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Adding a New MCP Tool](#adding-a-new-mcp-tool)
- [Working on the 3D Viewer](#working-on-the-3d-viewer)
- [Pull Request Process](#pull-request-process)

---

## Development Setup

```bash
git clone https://github.com/TutuBarry/abaqus-mcp-pro.git
cd abaqus-mcp-pro
pip install -e ".[dev]"
# optional: pip install -e ".[pywinauto]"  # for Windows GUI automation
```

### Viewer Frontend

The 3D viewer is a Vite + Three.js application. To work on it:

```bash
cd viewer
npm install
npm run dev          # hot-reload dev server on :5173
cd ..
pip install fastapi uvicorn
python viewer/viewer_server.py   # FastAPI backend on :8080
```

For production, build the frontend:

```bash
cd viewer && npx vite build
python viewer/serve_viewer.py   # serves built files on :8080
```

---

## Project Structure

```
abaqus-mcp-pro/
+-- src/abaqus_mcp_pro/          # Main Python package
|   +-- server.py                # MCP stdio server entry point
|   +-- tools.py                 # Core + extended MCP tool registrations
|   +-- prompts.py               # 13 MCP prompt definitions
|   +-- resources.py             # MCP resource definitions
|   +-- skills.py                # Skills knowledge base (74 resources)
|   +-- transport.py             # TCP socket / file IPC transport layer
|   +-- client.py                # TCP and file IPC client libraries
|   +-- protocol.py              # JSON wire protocol
|   +-- cli.py                   # CLI entry points (check, doctor, setup)
|   +-- agent.py                 # TCP bridge agent (runs inside Abaqus)
|   +-- gui_plugin.py            # Abaqus/CAE GUI plugin (AFX menu)
|   +-- file_ipc_plugin.py       # File IPC plugin (Abaqus-side)
|   +-- nogui.py                 # noGUI mode launcher
|   +-- abaqus_tools.py          # Core Abaqus operation wrappers
|   +-- abaqus_tools_extended.py # Extended Abaqus operations (50+)
|   +-- abaqus_docs.py           # Abaqus documentation search
|   +-- solver_diagnosis.py      # Solver Doctor: 40+ error patterns
|   +-- convergence_advisor.py   # Convergence fix suggestions
|   +-- silent_failures.py       # Silent failure detection
|   +-- odb_lens.py              # ODB Lens: KPI extraction
|   +-- capsule.py               # Experiment state tracking / diff
|   +-- contracts.py             # Physics contracts validation
|   +-- report.py                # Simulation report generation
|   +-- export_result_mesh.py    # ODB -> result_mesh.json (legacy)
|   +-- pywinauto_tools.py       # Windows GUI automation helpers
+-- viewer/                       # 3D browser viewer (Vite + Three.js)
|   +-- src/                     # Frontend source
|   |   +-- main.js              # Entry point (Vite)
|   |   +-- viewer3d.js          # Three.js scene management
|   |   +-- vtuparser.js         # VTK XML UnstructuredGrid (.vtu) parser
|   |   +-- vtkparser.js         # VTK PolyData (.vtp) parser
|   |   +-- loader.js            # Model loading UI
|   |   +-- ui.js                # UI controls and panels
|   |   +-- odbexport.js         # ODB export trigger
|   |   +-- measure.js           # Measurement tools
|   |   +-- colormaps.js         # Colormap definitions
|   |   +-- style.css            # Viewer styles
|   +-- export/                  # Python export utilities
|   |   +-- __init__.py
|   |   +-- export_to_vtk.py     # ODB -> VTU exporter (Liujie-SYSU based)
|   +-- serve_viewer.py          # One-click viewer server (http.server)
|   +-- viewer_server.py         # FastAPI viewer server (uvicorn)
|   +-- cache.py                 # Export cache manager
|   +-- package.json / vite.config.js  # Build tooling
|   +-- dist/                    # Vite production build output
|   +-- samples/                 # Sample VTU files for testing
+-- scripts/                      # noGUI launchers and utilities
+-- examples/                     # End-to-end example workflows
+-- tests/                        # Pytest test suite
+-- docs/                         # MkDocs documentation site
+-- skills/                       # AI skills knowledge base
+-- dev/                          # Development helper scripts
+-- MechAgent/                    # MechAgent integration (optional)
+-- pyproject.toml
+-- CHANGELOG.md
+-- CONTRIBUTING.md
+-- README.md / README_ZH.md
```

---

## Running Tests

```bash
# Run the full test suite
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/abaqus_mcp_pro --cov-report=term-missing

# Run a specific test file
pytest tests/test_solver_diagnosis.py -v
```

Tests are located in the `tests/` directory and use pytest. The test suite covers:

- **Unit tests** for individual modules (diagnosis, contracts, capsule, etc.)
- **Smoke tests** for server startup and basic tool registration
- **Skills** validation tests

> **Note:** Tests that require an active Abaqus license are marked with `@pytest.mark.abaqus`
> and are skipped in CI. Run them manually with `pytest -m abaqus` on a machine with Abaqus.

---

## Code Style

- **Python 3.10+** with full type annotations
- **Follow existing patterns** in the codebase -- consistency matters more than personal preference
- **Keep tools focused**: one MCP tool = one clear, composable purpose
- **Docstrings**: use Google-style docstrings for all public functions
- **No external dependencies** for Abaqus-side code (only stdlib); pip packages OK for host-side code
- **Async** for host-side I/O; synchronous for Abaqus kernel code

### Viewer Frontend

- ES modules (Vite build)
- Vanilla JS for the viewer core (no React/Vue framework overhead)
- Three.js for 3D rendering, OrbitControls for camera interaction
- Parse VTK XML directly in JS (vtuparser.js / vtkparser.js) -- no additional loaders

---

## Adding a New MCP Tool

Tools are defined in `src/abaqus_mcp_pro/tools.py` using the MCP Python SDK pattern.

1. **Implement the tool function** in `abaqus_tools.py` or `abaqus_tools_extended.py`
2. **Register it** in the `register_tools()` function in `tools.py`
3. **Add a prompt** (optional) in `prompts.py` if the tool benefits from guided usage
4. **Write tests** in `tests/`
5. **Update the README** Tools Reference table

```python
# Example: a tool function in abaqus_tools.py
def create_foobar(client, param1: str, param2: float = 1.0) -> str:
    """Do something useful in Abaqus.

    Args:
        client: Bridge client instance
        param1: Description of param1
        param2: Description of param2 (default: 1.0)

    Returns:
        str: Result description or status message
    """
    return client.execute("abaqus code here")
```

```python
# Registration in tools.py -> register_tools()
@server.tool()
async def create_foobar(param1: str, param2: float = 1.0) -> str:
    return _exec(_set_run_python(create_foobar, locals()))
```

---

## Working on the 3D Viewer

The viewer pipeline is: **ODB (.odb) -> export_to_vtk.py -> VTU (.vtu) -> vtuparser.js -> Three.js**

### Export Side (Python)

- `viewer/export/export_to_vtk.py` -- runs inside Abaqus Python (stdlib only)
- Reads ODB via `odbAccess.openOdb()`, extracts field data with element-nodal averaging
- Writes standard VTK XML UnstructuredGrid (.vtu) + model.json metadata
- To test without Abaqus, use sample files in `viewer/samples/`

### Viewer Side (JavaScript)

- `viewer/src/vtuparser.js` -- parses VTU XML into `{ positions, indices, cellTypes, fieldValues }`
- `viewer/src/viewer3d.js` -- main Three.js scene, handles rendering, picking, animation
- The viewer can also load legacy `.result_mesh.json` format (via main.js)

### Adding a New Field Variable

1. Add the field name to the `fields` list in export_to_vtk.py
2. The exporter extracts it from odb.steps[step].frames[frame].fieldOutputs[field]
3. The viewer parses it automatically from the VTU PointData section
4. No frontend changes needed unless you want custom rendering logic

---

## Pull Request Process

1. **Fork** the repository on GitHub
2. **Create a feature branch** from `main` (`git checkout -b feat/my-feature`)
3. **Make your changes**, keeping commits small and well-scoped
4. **Add tests** for new functionality -- bug fixes should include a regression test
5. **Run the tests**: `pytest tests/ -v`
6. **Update documentation** if the change affects user-facing behavior
7. **Submit a pull request** with a clear title and description:
   - What the change does
   - Why it is needed
   - Any breaking changes or migration notes

### PR Checklist

- [ ] Code follows project style (type annotations, docstrings)
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] New functions have corresponding tests
- [ ] README / docs updated if tool or behavior changed
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] Viewer frontend builds (`cd viewer && npx vite build`) if JS changed

---

## Reporting Issues

Open an issue on [GitHub Issues](https://github.com/TutuBarry/abaqus-mcp-pro/issues)
with the appropriate template (bug report, feature request, or question).
Include relevant information:

- Python and Abaqus versions
- Operating system
- Full error message and stack trace (if applicable)
- Steps to reproduce

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
