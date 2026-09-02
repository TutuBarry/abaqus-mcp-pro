# Abaqus Finite Element Skills

All finite element skills imported for this repository are organized here. The Abaqus-specific skills are grouped by workflow stage; the general FEA and FEniCS skills are kept under `reference/` because they can support Abaqus-oriented work but are not Abaqus-only.

## Categories

| Category | Skills |
| --- | --- |
| `core` | `abaqus` |
| `modeling` | `abaqus-geometry`, `abaqus-material`, `abaqus-mesh`, `abaqus-interaction` |
| `setup` | `abaqus-amplitude`, `abaqus-bc`, `abaqus-docs`, `abaqus-field`, `abaqus-load`, `abaqus-output`, `abaqus-step` |
| `analysis` | `abaqus-contact-analysis`, `abaqus-coupled-analysis`, `abaqus-dynamic-analysis`, `abaqus-fatigue-analysis`, `abaqus-modal-analysis`, `abaqus-static-analysis`, `abaqus-thermal-analysis` |
| `execution` | `abaqus-job`, `abaqus-export` |
| `postprocessing` | `abaqus-odb` |
| `optimization` | `abaqus-optimization`, `abaqus-shape-optimization`, `abaqus-topology-optimization` |
| `reference` | `fea-structural`, `fenics-fem` |

## Recommended Abaqus Chains

For a normal static analysis, use:

```text
core/abaqus
modeling/abaqus-geometry
modeling/abaqus-material
modeling/abaqus-mesh
setup/abaqus-load
setup/abaqus-bc
setup/abaqus-step
analysis/abaqus-static-analysis
execution/abaqus-job
postprocessing/abaqus-odb
```

For contact analysis, add `modeling/abaqus-interaction` and `analysis/abaqus-contact-analysis`.

For thermal or coupled work, use `analysis/abaqus-thermal-analysis` or `analysis/abaqus-coupled-analysis`.

For design iteration, add the relevant skill from `optimization/`.

## Client Setup

These are skill folders, not MCP servers. They should be used as instruction modules together with Abaqus, ANSYS, FEniCS, or other solver/MCP integrations.

### Codex

Copy the selected skill folders into your Codex skills directory, then restart Codex:

```powershell
$src = "E:\Code\text-to-cae\Skill\abaqus\analysis\abaqus-static-analysis"
$dst = "$env:USERPROFILE\.codex\skills\abaqus-static-analysis"
New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
Copy-Item -Recurse -Force $src $dst
```

Suggested prompt:

```text
Use the abaqus-static-analysis, abaqus-mesh, abaqus-job, and abaqus-odb skills. Build a complete Abaqus static-analysis workflow, run it if the Abaqus MCP or local Abaqus CLI is available, and report the exact files and commands used.
```

### Claude Code

For project-local use:

```powershell
New-Item -ItemType Directory -Force -Path .claude\skills | Out-Null
Copy-Item -Recurse -Force "E:\Code\text-to-cae\Skill\abaqus\modeling\abaqus-mesh" ".claude\skills\abaqus-mesh"
```

### Claude Desktop

Claude Desktop mainly uses MCP server configuration. Use these folders as reference context or copy them into a skill-aware companion client. When using them with an Abaqus MCP server, reference the relevant `SKILL.md` file and prompt:

```text
Follow the attached Abaqus finite element skill instructions. Use the configured MCP tools only for live solver operations, and state when an answer is only a modeling recommendation.
```

### Cursor and other clients

If the client supports project-local skills, copy selected folders into the client skills directory. If not, add the relevant `SKILL.md` files as project context and explicitly ask the agent to follow them.

## Licensing and Attribution

Each imported skill directory includes `UPSTREAM.md` with the source URL and import date. Where an upstream repository license file was available, it is included as `UPSTREAM_LICENSE` or `UPSTREAM_LICENSE.md`.

These are third-party public skills. Before redistributing modified versions or packaging them commercially, check the upstream repository and license terms.
