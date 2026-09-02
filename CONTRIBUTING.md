# Contributing to Abaqus MCP Pro

Thanks for your interest in contributing!

## Development Setup

`ash
git clone https://github.com/TutuBarry/abaqus-mcp-pro.git
cd abaqus-mcp-pro
pip install -e ".[dev]"
`

## Project Structure

`
abaqus-mcp-pro/
  src/abaqus_mcp_pro/   # Main package
    server.py           # MCP server (stdio entry)
    agent.py            # TCP bridge agent (runs inside Abaqus)
    tools.py            # MCP tool definitions
    prompts.py          # MCP prompt definitions
    resources.py        # MCP resource definitions
    skills.py           # Skills knowledge base
    transport.py        # TCP socket / file IPC transport
    client.py           # TCP and file IPC clients
    cli.py              # CLI: check, doctor, setup
    abaqus_tools.py     # Core Abaqus operations
    abaqus_tools_extended.py  # Extended Abaqus operations
    solver_diagnosis.py # Solver error diagnosis
    odb_lens.py         # ODB KPI extraction
    capsule.py          # Experiment state tracking
    contracts.py        # Physics contracts validation
    report.py           # Simulation report generation
    convergence_advisor.py  # Convergence troubleshooting
    silent_failures.py  # Silent failure detection
    gui_plugin.py       # Abaqus/CAE GUI plugin (AFX menu)
    file_ipc_plugin.py  # File IPC plugin (runs inside Abaqus)
    protocol.py         # Wire protocol
  scripts/              # Utility scripts
  skills/               # CAE Agent Hub skill definitions
  examples/             # Example workflows
  tests/                # Test suite
  dev/                  # Development tools
`

## Running Tests

`ash
pytest tests/ -v
`

## Code Style

- Python 3.10+ with type annotations
- Follow existing patterns in the codebase
- Keep tools focused: one tool = one clear purpose

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request with a clear description

## Questions?

Open an issue on GitHub or start a discussion.
