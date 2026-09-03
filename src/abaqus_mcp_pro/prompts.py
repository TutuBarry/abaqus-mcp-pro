"""MCP prompt definitions for Abaqus MCP server."""

from __future__ import annotations

from mcp.types import PromptMessage, TextContent


# ---------------------------------------------------------------------------
# Prompt functions (plain, no decorators)
# ---------------------------------------------------------------------------


def setup_optimization(
    optimization_type: str = "topology",
    objective: str = "minimize_compliance",
    volume_fraction: float = 0.3,
) -> list[PromptMessage]:
    """Guided optimization setup."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up an optimization analysis in Abaqus.

**Parameters:**
- Optimization type: {optimization_type}
- Objective: {objective}
- Volume fraction: {volume_fraction} (target: {volume_fraction * 100:.0f}% of original)

**Type selection:**
| Type | When to use | Requires |
|------|-------------|----------|
| Topology | Lightweight design, material distribution | Tosca license |
| Shape | Reduce stress concentration, refine fillets | Tosca license |
| Sizing | Optimize shell thickness, beam sections | Tosca license |

**Objective-constraint pairs:**
| Goal | Objective | Constraint |
|------|-----------|------------|
| Stiffest at weight | Minimize compliance | Volume <= {volume_fraction * 100:.0f}% |
| Lightest that works | Minimize volume | Compliance <= limit |
| Avoid resonance | Maximize frequency | Volume <= target |

**Important:** Requires full Abaqus license with Tosca module (NOT Learning Edition).

**My plan:**
1. Read abaqus://skills/topology-optimization or abaqus://skills/shape-optimization
2. Read abaqus://skills/optimization for base API
3. If topology: set up SIMP penalty, define frozen regions (BC/load areas), add manufacturing constraints
4. If shape: identify design surfaces, set movement limits, add smoothing
5. Submit OptimizationProcess and monitor convergence

Please confirm:
- Topology or shape optimization?
- What is the design space and what are the frozen regions?
- Volume fraction target (default: {volume_fraction * 100:.0f}%)?"""),
        ),
    ]


def setup_dynamic_analysis(
    event_type: str = "impact",
    duration: str = "10_ms",
    solver: str = "explicit",
) -> list[PromptMessage]:
    """Guided dynamic analysis setup."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a dynamic analysis in Abaqus.

**Parameters:**
- Event type: {event_type}
- Duration: {duration}
- Solver: {solver}

**Solver selection:**
| Factor | Explicit | Implicit |
|--------|----------|----------|
| Time scale | Short (us to ms) | Longer (ms to s) |
| Best for | Impact, crash | Vibration, long transient |
| Contact | Natural handling | Needs care |
| Memory | Lower | Higher |

**Decision rule:**
- Event < 10ms with impact/contact -> Explicit
- Event > 100ms without severe nonlinearity -> Implicit

**Critical requirements:**
- Material MUST have density (required for mass matrix)
- Initial conditions: velocity for drop tests
- Output: S, U, V, A, PEEQ, ALLKE, ALLIE, ETOTAL

**My plan:**
1. Read abaqus://skills/dynamic-analysis for the full workflow
2. Read abaqus://skills/material to ensure density is defined
3. Set time period = {duration}
4. Define initial conditions (velocity, position)
5. Request energy output for balance check
6. Submit and verify energy balance (ETOTAL constant)

Please confirm:
- Is this an impact, drop test, or vibration?
- What is the event duration?
- Any initial velocity?"""),
        ),
    ]


def setup_coupled_analysis(
    coupling_type: str = "sequential",
    temperature: float = 100.0,
    material: str = "steel",
) -> list[PromptMessage]:
    """Guided coupled thermomechanical analysis."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a coupled thermomechanical analysis in Abaqus.

**Parameters:**
- Coupling type: {coupling_type}
- Temperature: {temperature} C
- Material: {material}

**Coupling type decision:**
| Scenario | Type | Approach |
|----------|------|----------|
| Heat causes stress, no feedback | One-way | Sequential |
| Friction/plastic work generates heat | Two-way | Fully coupled |
| Simple thermal expansion | One-way | Sequential (simpler) |

**Material properties required:**
Both mechanical AND thermal:
- Mechanical: E, nu
- Thermal: k (conductivity), alpha (expansion coefficient), T_ref
- For transient: cp (specific heat), density

**Typical steel values (SI-mm):**
E = 210000 MPa, nu = 0.3, k = 50 mW/(mm-K), alpha = 12e-6 /K

**Coupled elements:**
| Element | Use |
|---------|-----|
| C3D8T | 8-node coupled brick (general) |
| C3D8RT | Reduced integration (faster) |
| C3D10MT | 10-node tet (complex geometry) |

**My plan:**
1. Read abaqus://skills/coupled-analysis for the full workflow
2. Read abaqus://skills/thermal-analysis if sequential (thermal first)
3. Define material with BOTH mechanical and thermal properties
4. Set initial temperature = T_ref (for zero initial stress)
5. Use coupled elements (C3D*T) for fully coupled
6. Request THE (thermal strain), E (total strain), S (stress)

Please confirm:
- One-way (sequential) or two-way (fully coupled)?
- Reference temperature (T_ref)?
- Any mechanical loads in addition to thermal?"""),
        ),
    ]


def setup_fatigue_analysis(
    fatigue_type: str = "high_cycle",
    mean_stress_correction: str = "goodman",
    target_cycles: int = 1000000,
) -> list[PromptMessage]:
    """Guided fatigue analysis setup."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a fatigue analysis.

**Parameters:**
- Fatigue type: {fatigue_type}
- Mean stress correction: {mean_stress_correction}
- Target cycles: {target_cycles:,}

**Important: Abaqus has limited native fatigue capabilities.**
The typical workflow is:
1. Run structural analysis in Abaqus (stress/strain results)
2. Extract stress history from ODB
3. Apply fatigue criteria externally (Basquin, Miner's rule)

For full fatigue analysis, consider: fe-safe, nCode, FEMFAT.

**Fatigue approach:**
| Approach | When | Data needed |
|----------|------|-------------|
| Stress-life (S-N) | High-cycle (N > 10^4) | S-N curve |
| Strain-life (e-N) | Low-cycle (N < 10^4) | Coffin-Manson params |
| Fracture mechanics | Crack growth | da/dN curve |

**Mean stress correction:**
| Method | Use case |
|--------|----------|
| Goodman | Conservative, tensile mean |
| Gerber | Less conservative |
| Soderberg | Very conservative |
| SWT | Strain-life with mean stress |

**Key parameters:**
| Parameter | Typical | Notes |
|-----------|---------|-------|
| S-N slope (b) | 0.08-0.15 | Lower = longer life |
| Endurance limit | 40-50% UTS (steel) | Below this = infinite life |
| Fatigue notch factor (Kf) | 1.0-3.0 | Kf = 1 + q(Kt-1) |

**My plan:**
1. Read abaqus://skills/fatigue-analysis for the workflow
2. Read abaqus://skills/static-analysis for the base stress analysis
3. Run static analysis to get peak stress
4. Extract stress at critical location
5. Apply {mean_stress_correction} correction
6. Calculate life using Basquin equation
7. Apply Miner's rule for cumulative damage

Please confirm:
- High-cycle (S-N) or low-cycle (e-N)?
- Do you have S-N curve data for the material?
- Is the loading constant amplitude or variable?"""),
        ),
    ]


def setup_static_analysis(
    material: str = "steel",
    geometry: str = "tensile_specimen",
    load_type: str = "tension",
) -> list[PromptMessage]:
    """Guided workflow for static stress analysis."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a static stress analysis in Abaqus.

**What I know so far:**
- Material: {material}
- Geometry: {geometry}
- Load type: {load_type}

**What I need to confirm with the user:**
1. Exact dimensions of the {geometry} (length, width, thickness in mm)
2. Material properties: E, nu, density, yield stress (if I should use defaults for {material}, I'll look them up from abaqus://skills/material)
3. Load magnitude: force in N or pressure in MPa
4. Boundary conditions: which faces are fixed? Is it one end fixed (cantilever) or both ends?
5. Mesh element size: coarse (quick check), medium (general), or fine (accurate)?

**My plan:**
1. Read abaqus://skills/static-analysis for the workflow
2. Read abaqus://skills/material for {material} properties
3. Read abaqus://skills/units to confirm mm-tonne-s-N-MPa
4. Create geometry, assign material, mesh, apply BCs and loads
5. Submit job and extract results

Please confirm or correct the parameters above, then I'll proceed."""),
        ),
    ]


def setup_contact_analysis(
    parts: str = "two_bodies",
    contact_type: str = "friction",
    friction_coefficient: float = 0.3,
) -> list[PromptMessage]:
    """Guided workflow for contact analysis."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a contact analysis in Abaqus.

**What I know so far:**
- Parts: {parts}
- Contact type: {contact_type}
- Friction coefficient: {friction_coefficient}

**What I need to confirm:**
1. Which surfaces are in contact? (master/slave assignment)
2. Is there an initial gap or interference fit?
3. If {contact_type} == "friction", is {friction_coefficient} correct? (Typical: dry steel 0.3-0.5, lubricated 0.1-0.2)
4. What loads push the parts together?
5. Any additional BCs beyond contact?

**My plan:**
1. Read abaqus://skills/contact-analysis for the full workflow
2. Read abaqus://skills/interaction for master/slave rules
3. Use nlgeom=ON, smaller increments, contact outputs (CSTRESS, CDISP, COPEN)
4. Verify convergence after job submission

Please confirm the parameters."""),
        ),
    ]


def define_material(
    material_name: str = "steel",
    analysis_type: str = "static",
) -> list[PromptMessage]:
    """Guided material definition."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to define material properties for: {material_name}

**Analysis type:** {analysis_type}

**Required properties by analysis type:**
| Analysis | Required | Optional |
|----------|----------|----------|
| Static stress | E, nu | - |
| Static + gravity | E, nu, density | - |
| Plastic | E, nu, sigma_y | density |
| Modal | E, nu, density | - |
| Dynamic | E, nu, density | Plasticity |
| Thermal stress | E, nu, alpha | k, cp |
| Thermal only | k | cp, density |

**My plan:**
1. Read abaqus://skills/material for the exact property values for {material_name}
2. Read abaqus://skills/units to confirm units (E in MPa, density in tonne/mm^3)
3. Create the material, assign section, verify all cells have section assigned

Please confirm:
- Material name: {material_name}
- Analysis type: {analysis_type} (affects which properties are required)
- Any special material behavior (plasticity, thermal expansion, etc.)?"""),
        ),
    ]


def setup_mesh(
    element_type: str = "C3D8R",
    element_size: float = 5.0,
    geometry_complexity: str = "simple",
) -> list[PromptMessage]:
    """Guided meshing workflow."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to mesh a part in Abaqus.

**Current settings:**
- Element type: {element_type}
- Element size: {element_size} mm
- Geometry complexity: {geometry_complexity}

**Element type selection guide:**
| Geometry | Recommended | Notes |
|----------|-------------|-------|
| Simple box/prism | C3D8R (hex, reduced) | Fast, accurate |
| Complex freeform | C3D10 (tet, quadratic) | Meshes anything |
| Thin-walled (t/L < 0.1) | S4R (shell) | Plates, sheet metal |
| Slender (L/d > 10) | B31 (beam) | Frames, trusses |

**Size guidelines:**
| Use Case | Size (mm) |
|----------|-----------|
| Quick feasibility | 10-20 |
| General analysis | 3-5 |
| Stress concentrations | 1-2 |

**Learning Edition limit:** max 1000 nodes.

**My plan:**
1. Read abaqus://skills/mesh for detailed guidance
2. Check if {element_type} is appropriate for {geometry_complexity} geometry
3. Estimate node count: (L/size+1) * (W/size+1) * (H/size+1)
4. Generate mesh, verify quality

Please confirm element type and size, or provide specific requirements."""),
        ),
    ]


def debug_job(
    job_name: str = "",
    error_type: str = "unknown",
) -> list[PromptMessage]:
    """Guided job debugging."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""An Abaqus job has failed and needs debugging.

**Job:** {job_name or "(not specified)"}
**Error type:** {error_type}

**Debug checklist:**
1. Check abaqus://skills/job for common failure modes
2. Read .msg file for solver errors
3. Read .sta file for progress
4. Check .dat file for warnings

**Common failures and solutions:**
| Error | Cause | Solution |
|-------|-------|----------|
| Zero pivot | Rigid body motion | Add more BCs |
| Negative eigenvalue | Buckling/instability | Check BCs, add stabilization |
| Too many increments | Load too large | Reduce load, more increments |
| Time increment too small | Severe nonlinearity | Add stabilization, check material |
| Memory exceeded | Mesh too fine | Increase element size |
| License not available | - | Wait or check license server |

**My plan:**
1. Run monitor_job_status to get .sta and .msg diagnostics
2. Read abaqus://skills/job for troubleshooting guidance
3. If mesh-related, read abaqus://skills/mesh
4. If BC-related, read abaqus://skills/boundary-condition
5. Fix the issue and resubmit

What is the job name and what error did you see?"""),
        ),
    ]


def extract_odb_results(
    odb_path: str = "",
    output_variable: str = "S",
    frame: str = "last",
) -> list[PromptMessage]:
    """Guided ODB result extraction."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to extract results from an ODB file.

**ODB path:** {odb_path or "(need to specify)"}
**Output variable:** {output_variable}
**Frame:** {frame}

**Common output variables:**
| Variable | Description | Use case |
|----------|-------------|----------|
| S | Stress (Mises, components) | Stress analysis |
| U | Displacement | Deformation |
| RF | Reaction forces | Force balance |
| E | Total strain | Strain analysis |
| PEEQ | Equivalent plastic strain | Plasticity |
| NT | Nodal temperature | Thermal |
| HFL | Heat flux | Thermal |

**Frame selection:**
| Scenario | Frame |
|----------|-------|
| Final results | step.frames[-1] |
| All time history | Loop all frames |
| Specific time | Find by frameValue |

**My plan:**
1. Read abaqus://skills/odb for extraction patterns
2. Use inspect_odb to get the structure first
3. Extract {output_variable} from the {frame} frame
4. For max values: loop field values, find max
5. For reaction forces: sum across all nodes

Please confirm the ODB path and which variable you need."""),
        ),
    ]


def setup_modal_analysis(
    num_modes: int = 10,
    boundary_condition: str = "cantilever",
    material: str = "steel",
) -> list[PromptMessage]:
    """Guided modal analysis setup."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a modal analysis in Abaqus.

**Parameters:**
- Number of modes: {num_modes}
- Boundary condition: {boundary_condition}
- Material: {material}

**Critical requirements:**
- Material MUST have density (required for mass matrix)
- NO loads needed for eigenvalue extraction
- BCs define the modal boundary

**BC configurations:**
| Configuration | Expected result |
|---------------|----------------|
| Free-free (no BCs) | 6 rigid body modes at ~0 Hz, then elastic |
| Cantilever (one end fixed) | First mode is bending |
| Simply supported | Bending, plate modes |
| Fixed-fixed | Higher frequencies than cantilever |

**My plan:**
1. Read abaqus://skills/modal-analysis for the full workflow
2. Read abaqus://skills/material to ensure density is defined for {material}
3. Create FrequencyStep with numEigen={num_modes}, LANCZOS solver
4. Apply {boundary_condition} BCs
5. Submit and extract eigenfrequencies from frame descriptions

Please confirm the number of modes and boundary condition."""),
        ),
    ]


def setup_thermal_analysis(
    analysis_type: str = "steady_state",
    material: str = "steel",
    boundary_temp: float = 100.0,
) -> list[PromptMessage]:
    """Guided thermal analysis setup."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text=f"""I need to set up a thermal analysis in Abaqus.

**Parameters:**
- Analysis type: {analysis_type}
- Material: {material}
- Boundary temperature: {boundary_temp} C

**Decision: Steady-state vs Transient**
| User wants | Analysis type |
|------------|---------------|
| Final equilibrium temperature | STEADY_STATE |
| Temperature vs time history | TRANSIENT |
| Cool-down or heat-up time | TRANSIENT |

**Thermal material properties needed:**
| Property | Required for | Units (SI-mm) |
|----------|--------------|---------------|
| Conductivity (k) | All thermal | mW/(mm-K) |
| Specific heat (cp) | Transient | mJ/(tonne-K) |
| Density | Transient | tonne/mm^3 |

**Thermal BC types:**
| BC | Use for |
|-----|---------|
| TemperatureBC | Fixed temperature surface |
| FilmCondition | Convection to ambient |
| SurfaceHeatFlux | Heat input |
| RadiationToAmbient | Radiation cooling |

**My plan:**
1. Read abaqus://skills/thermal-analysis for the full workflow
2. Read abaqus://skills/material for thermal properties of {material}
3. Use heat transfer elements (DC3D8, not C3D8)
4. Apply temperature BC of {boundary_temp} C
5. Request NT (temperature), HFL (heat flux) outputs
6. If coupled with stress, read abaqus://skills/coupled-analysis

Please confirm:
- Steady-state or transient?
- Which surfaces have fixed temperature?
- Any convection or heat flux BCs?"""),
        ),
    ]


def session_workflow() -> list[PromptMessage]:
    """Master workflow prompt."""
    return [
        PromptMessage(
            role="user",
            content=TextContent(text="""I'm starting an Abaqus session. Here's my workflow checklist:

**Step 1: Check connection**
- Call check_abaqus_connection to verify the bridge is active
- Read abaqus://session-telemetry for detailed status

**Step 2: Understand the current model**
- Call get_model_info to see existing parts, materials, steps, jobs
- Check what's already built vs what needs to be created

**Step 3: Gather requirements**
- What analysis type? (static, modal, contact, dynamic, thermal, coupled)
- What material? (steel, aluminum, custom)
- What geometry? (beam, plate, cylinder, complex)
- What loads and BCs?

**Step 4: Consult relevant skills**
- Read abaqus://skills/index for the full skill catalog
- Read the specific skill for the analysis type (e.g., abaqus://skills/static-analysis)
- Read abaqus://skills/units for unit system
- Read abaqus://skills/material for material properties

**Step 5: Build the model incrementally**
- Use run_python with small, validated chunks
- Create named sets/surfaces for BCs and loads
- Verify each step before proceeding

**Step 6: Submit and verify**
- Call submit_job or run_python to submit
- Call monitor_job_status to check progress
- Call capture_viewport to visualize results

**Step 7: Extract results**
- Read abaqus://skills/odb for extraction patterns
- Use inspect_odb to explore the output database
- Extract stress, displacement, reaction forces as needed

What would you like to do?"""),
        ),
    ]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_prompts(mcp) -> None:
    """Register all MCP prompts with the given MCPServer instance.

    Args:
        mcp: An MCPServer instance.
    """
    mcp_prompt = mcp.prompt()
    mcp_prompt(setup_optimization)
    mcp_prompt(setup_dynamic_analysis)
    mcp_prompt(setup_coupled_analysis)
    mcp_prompt(setup_fatigue_analysis)
    mcp_prompt(setup_static_analysis)
    mcp_prompt(setup_contact_analysis)
    mcp_prompt(define_material)
    mcp_prompt(setup_mesh)
    mcp_prompt(debug_job)
    mcp_prompt(extract_odb_results)
    mcp_prompt(setup_modal_analysis)
    mcp_prompt(setup_thermal_analysis)
    mcp_prompt(session_workflow)
