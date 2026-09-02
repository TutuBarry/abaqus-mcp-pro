import sys
import os

filepath = os.path.join(os.path.dirname(__file__), "..", "src", "abaqus_mcp_pro", "skills.py")
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

new_skills = """,
    "skills/amplitude": \"""
# Abaqus Amplitude Definitions

## Amplitude Types
| User Describes | Amplitude Type | Key Parameters |
|----------------|----------------|----------------|
| Linear increase/decrease | TabularAmplitude | Time-value pairs |
| Smooth transition | SmoothStepAmplitude | Time-value pairs |
| Sinusoidal/harmonic | PeriodicAmplitude | Frequency, coefficients |
| Exponential decay | DecayAmplitude | Initial, decayTime |
| Custom time history | TabularAmplitude | User-provided data |

## Common Load Profiles
| Profile | Data Pattern | Use Case |
|---------|--------------|----------|
| Linear ramp | (0,0), (1,1) | Quasi-static loading |
| Ramp up/down | (0,0), (0.5,1), (1,0) | Load cycle |
| Hold at peak | (0,0), (0.1,1), (1,1) | Ramp then sustain |
| Triangular pulse | (0,0), (0.001,1), (0.002,0) | Impact/impulse |
| Step function | (0,0), (0,1), (1,1) | Sudden application |

## Time Reference
| Setting | When |
|---------|------|
| timeSpan=STEP | Time relative to current step (most common) |
| timeSpan=TOTAL | Time from analysis beginning (multi-step) |

## Smooth vs Tabular
| Use SmoothStepAmplitude | Use TabularAmplitude |
|-------------------------|----------------------|
| Dynamic analysis (avoid shocks) | Static analysis |
| Convergence issues from sudden loads | Exact load profile needed |
| Continuous derivatives required | Step functions needed |
\""",
    "skills/field": \"""
# Abaqus Predefined Fields and Initial Conditions

## Field Types
| User Need | Field Type | Typical Use |
|-----------|------------|-------------|
| Starting temperature | Temperature | Thermal stress from uniform T |
| Residual stress | Stress | Pre-stressed members |
| Impact velocity | Velocity | Explicit dynamics |
| From other analysis | Predefined Temperature | Sequential thermal-structural |
| Custom variable | Predefined Field | User-defined behaviors |

## Distribution Types
| Type | When to Use |
|------|-------------|
| UNIFORM | Same value everywhere |
| FROM_FILE | Import from ODB or FIL |
| ANALYTICAL_FIELD | Expression-based (X, Y, Z) |
| USER_DEFINED | Via user subroutine |

## Sequential Thermal-Structural
1. Run thermal analysis, save ODB
2. Import temperature as predefined field in structural model
3. Temperature causes thermal strain (requires expansion coefficient)

## Key Parameters
| Parameter | Notes |
|-----------|-------|
| createStepName | 'Initial' for initial conditions, step name for predefined |
| distributionType | UNIFORM, FROM_FILE, ANALYTICAL_FIELD |
| fileName | ODB path for FROM_FILE distribution |
| beginStep/endStep | Frame selection for ODB import |
\""",
    "skills/contact-analysis": \"""
# Abaqus Contact Analysis Workflow

## Prerequisites
- Separate parts exist (at least two bodies)
- Parts positioned in assembly with appropriate gap/interference
- Material properties defined for all parts

## Master/Slave Selection
| Role | Should Be |
|------|-----------|
| Master | Stiffer material, coarser mesh |
| Slave | Softer material, finer mesh |

## Contact Type Selection
| Scenario | Approach |
|----------|----------|
| Permanently bonded surfaces | Tie constraint |
| Sliding with friction | Surface-to-surface contact |
| Frictionless contact | Surface-to-surface, no tangential |
| Many bodies touching | General contact |
| Surface folding on itself | Self-contact |

## Friction Coefficients
| Interface | Typical Value |
|-----------|---------------|
| Frictionless | 0.0 |
| Lubricated steel | 0.1-0.2 |
| Dry steel-on-steel | 0.3-0.5 |
| Rubber on metal | 0.5-0.8 |

## Step Settings for Contact
- nlgeom=ON (required)
- Smaller initial increment (0.01-0.1)
- More increments allowed (100+)
- Minimum increment for convergence (1e-8 to 1e-12)

## Contact Output Variables
| Variable | Description |
|----------|-------------|
| CSTRESS | Contact pressure and shear |
| CDISP | Contact displacement |
| COPEN | Gap opening distance |
| CSLIP | Accumulated slip |

## Troubleshooting
| Problem | Cause | Solution |
|---------|-------|----------|
| Severe discontinuity | Contact chattering | Add stabilization, smaller increments |
| Too much penetration | Wrong master/slave | Swap roles, refine slave mesh |
| Contact not detected | Surfaces too far | Use adjust=ON |
| Convergence failure | Difficult nonlinearity | Smaller increments, check friction |
\""",
    "skills/dynamic-analysis": \"""
# Abaqus Dynamic Analysis

## Explicit vs Implicit
| Factor | Explicit | Implicit |
|--------|----------|----------|
| Time scale | Short (us to ms) | Longer (ms to s) |
| Step size | Automatic (very small) | User-controlled |
| Nonlinearity | Handles well | May need iterations |
| Memory | Lower | Higher |
| Contact | Natural handling | Needs care |
| Best for | Impact, crash | Vibration, long transient |

Decision rule: Event < 10ms with impact/contact -> Explicit; Event > 100ms without severe nonlinearity -> Implicit

## Prerequisites
- Material MUST have density defined (required for mass matrix)
- Understand event duration and loading type

## Typical Event Durations
| Event Type | Typical Duration |
|------------|------------------|
| High-speed impact | 0.1-10 ms |
| Drop test | 1-100 ms |
| Blast loading | 1-50 ms |
| Seismic/vibration | 1-100 s |

## Key Output Variables
| Variable | Description |
|----------|-------------|
| S | Stress |
| U | Displacement |
| V | Velocity |
| A | Acceleration |
| PEEQ | Plastic strain |
| ALLKE | Kinetic energy (explicit) |
| ALLIE | Internal energy (explicit) |
| ETOTAL | Total energy (explicit) |

## Mass Scaling (Explicit)
| Option | Effect | When |
|--------|--------|------|
| None | True inertia | Very short events, accuracy critical |
| At beginning | Scale once | Quasi-static explicit |
| Throughout | Continuous scaling | When inertia less important |

Warning: Mass scaling speeds up analysis but affects inertial response.

## Validation
- Energy balance (ETOTAL approximately constant for explicit)
- Stable time increment
- Results physically reasonable
\""",
    "skills/thermal-analysis": \"""
# Abaqus Heat Transfer Analysis

## Analysis Type Selection
| User Wants | Analysis Type |
|------------|---------------|
| Final equilibrium temperature | STEADY_STATE |
| Temperature vs time history | TRANSIENT |
| Cool-down or heat-up time | TRANSIENT |

## Thermal Material Properties
| Property | Required For | Units (SI-mm) |
|----------|--------------|---------------|
| Conductivity (k) | All thermal | mW/(mm.K) |
| Specific heat (cp) | Transient | mJ/(tonne.K) |
| Density (rho) | Transient | tonne/mm^3 |

## Common Materials (SI-mm units)
| Material | k | cp | rho |
|----------|---|----|-----|
| Steel | 50 | 5.0e11 | 7.85e-9 |
| Aluminum | 167 | 9.0e11 | 2.70e-9 |
| Copper | 385 | 3.85e11 | 8.96e-9 |

## Thermal Boundary Conditions
| BC Type | Use For | Required Inputs |
|---------|---------|-----------------|
| TemperatureBC | Fixed temperature surface | Temperature value |
| FilmCondition | Convection to ambient | Film coeff, sink temp |
| SurfaceHeatFlux | Heat input | Flux magnitude (mW/mm^2) |
| RadiationToAmbient | Radiation cooling | Emissivity, ambient temp |
| BodyHeatFlux | Internal heat generation | Volumetric heat rate |

## Heat Transfer Elements
| Element | Use |
|---------|-----|
| DC3D8 | Standard 8-node hex (recommended) |
| DC3D4 | 4-node tet (for complex geometry) |
| DC3D20 | 20-node hex (high accuracy) |

Note: Heat transfer elements (DC*) are different from structural elements (C3D*).

## Key Output Variables
| Variable | Description |
|----------|-------------|
| NT | Nodal temperature |
| HFL | Heat flux vector |
| RFL | Reaction heat flux |
| HFLM | Heat flux magnitude |

## Troubleshooting
| Problem | Cause | Solution |
|---------|-------|----------|
| Temperature oscillation | Large increments in transient | Reduce maxInc or deltmx |
| Non-physical temperature | Unit mismatch | Verify k, cp, rho units |
| No heat flow | Missing BC or bad region | Check boundary conditions |
\""",
    "skills/fatigue-analysis": \"""
# Abaqus Fatigue Analysis

## Important: Abaqus Fatigue Limitations
Abaqus has limited native fatigue capabilities. The typical workflow is:
1. Run structural analysis in Abaqus (stress/strain results)
2. Extract stress history from ODB
3. Apply fatigue criteria externally (Basquin, Miner's rule)

For full fatigue analysis, consider: fe-safe, nCode, FEMFAT.

## Fatigue Approach Selection
| Approach | When to Use | Data Needed |
|----------|-------------|-------------|
| Stress-life (S-N) | High-cycle (N > 10^4) | S-N curve |
| Strain-life (e-N) | Low-cycle (N < 10^4) | Coffin-Manson params |
| Fracture mechanics | Crack growth | da/dN curve |

## Mean Stress Correction
| Method | Use Case |
|--------|----------|
| Goodman | Conservative, tensile mean |
| Gerber | Less conservative |
| Soderberg | Very conservative |
| SWT | Strain-life with mean stress |

## Key Parameters
| Parameter | Typical Values | Notes |
|-----------|----------------|-------|
| S-N slope (b) | 0.08-0.15 | Lower = longer life |
| Endurance limit | 40-50% UTS (steel) | Stress below which infinite life |
| Fatigue notch factor (Kf) | 1.0-3.0 | Kf = 1 + q(Kt-1) |
| Notch sensitivity (q) | 0.7-0.95 | Higher for stronger steels |

## Workflow
1. Run stress analysis with S, E, PEEQ output
2. Identify critical location (max stress, stress concentrations)
3. Extract stress history (constant or variable amplitude)
4. Apply fatigue criteria (S-N curve, Goodman correction)
5. Calculate life using Basquin equation and Miner's rule

## Troubleshooting
| Problem | Cause | Solution |
|---------|-------|----------|
| Unrealistically short life | Stress singularity | Use Kf correction |
| Wrong units | MPa vs Pa mismatch | Verify stress units match S-N data |
| Unconservative prediction | Missing mean stress | Apply Goodman/Gerber correction |
\""",
    "skills/coupled-analysis": \"""
# Abaqus Coupled Field Analysis

## Coupled Analysis Types
| Analysis | Use Case |
|----------|----------|
| Coupled temp-displacement | Thermal stress (temperature causes deformation) |
| Pore pressure (soil) | Geotechnical consolidation |
| Piezoelectric | Sensors, actuators |
| Structural-acoustic | Noise, vibration in fluids |
| Thermo-electrical | Joule heating, electronics |

## Thermal-Structural (Most Common)
| Property | Thermal | Structural |
|----------|---------|-------------|
| Required material | k (+ cp, rho for transient) | E, nu (+ alpha for thermal strain) |
| Element type | DC3D8 | C3D8T |
| BC type | Temperature, Film, HeatFlux | Fixed, Force, Pressure |
| Output | NT, HFL | S, U (+ thermal strain) |

## Sequential vs Fully Coupled
| Approach | When | Advantage |
|----------|------|-----------|
| Sequential | Weak coupling (T affects stress, stress doesn't affect T) | Faster, simpler |
| Fully coupled | Strong coupling (mutual influence) | More accurate |

## Workflow for Thermal-Structural
1. Run thermal analysis (steady-state or transient)
2. Save ODB with temperature field
3. Create structural model with same mesh
4. Import temperature as predefined field
5. Run structural analysis with thermal expansion

## Common Pitfalls
| Problem | Cause | Solution |
|---------|-------|----------|
| No thermal strain | Missing alpha | Add expansion coefficient to material |
| Temperature mismatch | Mesh incompatibility | Use same mesh or mapping tolerance |
| Wrong element type | Using C3D8 instead of C3D8T | Switch to coupled elements |
\""",
    "skills/optimization": \"""
# Abaqus Optimization (Tosca)

## Important: License Required
Topology/Shape optimization requires a full Abaqus license with Tosca module. NOT available in Learning Edition.

## Prerequisites
- Working static analysis that converges
- Appropriate mesh density
- Full Abaqus license with Tosca

## Objective-Constraint Pairs
| User Wants | Objective | Constraint |
|------------|-----------|------------|
| Lightest structure that's stiff enough | Minimize volume | Compliance <= limit |
| Stiffest structure at given weight | Minimize compliance | Volume <= 30% |
| Avoid resonance | Maximize frequency | Volume <= target |
| Reduce peak stress | Minimize max stress | Volume <= target |

Most common: Minimize compliance with volume <= 30%

## Design Responses
| Response | When to Use |
|----------|-------------|
| VOLUME | Almost always (volume constraint) |
| STRAIN_ENERGY | Stiffness optimization |
| EIGENFREQUENCY | Vibration/resonance |
| STRESS | Stress-constrained design |
| DISPLACEMENT | Deflection limit |

## Key Parameters
| Parameter | Recommended | Notes |
|-----------|-------------|-------|
| SIMP penalty | 3.0 | Higher = sharper boundaries |
| Volume fraction | 0.3-0.4 | Start conservative |
| Min member size | 3x mesh size | Prevents checkerboard |
| Design cycles | 30-50 | More for complex geometry |

## Manufacturing Constraints
| Constraint | Purpose |
|------------|---------|
| Min member size | Prevents thin, unmanufacturable features |
| Symmetry | Mirrors design about plane |
| Draw direction | Enables mold/casting extraction |
| Overhang angle | For additive manufacturing |

## Always Freeze
- BC application regions (mounting points)
- Load application regions
- Functional surfaces (mating interfaces)

## Troubleshooting
| Problem | Cause | Solution |
|---------|-------|----------|
| Checkerboard pattern | No min member size | Add GeometricRestriction |
| Disconnected result | Load path broken | Freeze more regions |
| Not converging | Constraint too tight | Relax volume fraction |
| License error | No Tosca module | Requires full Abaqus |
\""",
    "skills/topology-optimization": \"""
# Abaqus Topology Optimization Workflow

## Phases

### Phase 1: Setup Base Model
1. Geometry - Design space with partitions for frozen regions
2. Material - Elastic properties + density (required for TO)
3. Mesh - Fine mesh (2-5mm typical for TO)
4. BCs - Fixed supports (these regions become frozen)
5. Loads - Applied forces (these regions become frozen)
6. Step - Static step for stiffness optimization

### Phase 2: Configure Optimization
1. Create TopologyTask with SIMP interpolation
2. Define design responses (volume, strain energy)
3. Set objective function (minimize compliance)
4. Add constraints (volume <= target fraction)
5. Define frozen regions (BC and load attachment areas)
6. Add manufacturing constraints (min member size)

### Phase 3: Run and Post-Process
1. Submit OptimizationProcess
2. View density distribution in ODB
3. Export STL at density threshold (0.3-0.5 typical)

## Volume Fraction Guide
| Fraction | Use Case |
|----------|----------|
| 20-30% | Aggressive (aerospace) |
| 30-40% | Balanced (general) |
| 40-50% | Conservative (safety-critical) |

## Validation
| Stage | Check |
|-------|-------|
| Base model | Static analysis runs, results sensible |
| After iteration 5 | Objective decreasing, no disconnection |
| Convergence | Objective stable (< 0.1% change) |
| Final design | Load path intact, no floating regions |
\""",
    "skills/shape-optimization": \"""
# Abaqus Shape Optimization

## When to Use
Shape optimization modifies surface geometry to reduce stress concentrations or improve performance. Use for:
- Reducing stress at fillets/notches
- Optimizing surface curvature
- Minimizing peak stress while maintaining volume

## vs Topology Optimization
| Feature | Topology | Shape |
|---------|----------|-------|
| What changes | Material distribution | Surface geometry |
| Result | Organic structure | Smoother surfaces |
| Mesh | Fixed FE mesh | Variable surface nodes |
| Manufacturing | Additive | Casting, machining, forging |

## Workflow
1. Run baseline analysis to identify stress concentrations
2. Define design region (surfaces to modify)
3. Set objective (minimize max stress) and constraints (volume, min radius)
4. Define design variables (node movement limits)
5. Run optimization
6. Export smoothed geometry

## Key Parameters
| Parameter | Recommended |
|-----------|-------------|
| Max node movement | 5-10% of feature size |
| Smoothing iterations | 3-5 |
| Min radius constraint | Manufacturing tool radius |

## Common Uses
- Fillet radius optimization
- Notch stress reduction
- Forging preform design
- Sheet metal bead optimization
\""",
    "skills/export": \"""
# Abaqus Export Operations

## Format Selection
| Need | Format | Requires |
|------|--------|----------|
| 3D printing | STL (double precision) | Meshed part |
| CAD exchange | STEP | Part geometry |
| Legacy CAD | IGES | Part geometry |
| Data analysis | CSV | ODB file |
| Archive/HPC | INP | Complete model |
| Reports/images | PNG/SVG | GUI session |

## Export Targets
| Source | Available Formats |
|--------|------------------|
| Part geometry | STL, STEP, IGES, SAT |
| Assembly | STL, SAT |
| Mesh data | CSV (nodes, elements) |
| Results (U, S, RF) | CSV |
| Time history | CSV |
| Model definition | INP |
| Topology result | STL (with density threshold) |

## Common Workflows

### Export to STL
1. Mesh the part
2. Use writeSTL (double precision for accuracy)
3. Verify file size reasonable

### Export Results to CSV
1. Open ODB with readOnly=True
2. Navigate to target step/frame
3. Extract field output (U, S, etc.)
4. Loop through values, write CSV rows
5. Close ODB

### Generate Input File
1. Create job with model name
2. Call writeInput() - creates JobName.inp

### Export TO Result
1. Locate TO ODB (usually Optimization/TOSCA_POST/Optimization.odb)
2. Set density threshold (0.3-0.5)
3. Export STL

## Troubleshooting
| Problem | Cause | Solution |
|---------|-------|----------|
| Cannot write STL - no mesh | Part not meshed | Mesh part first |
| STEP export failed | Invalid geometry | Try IGES or SAT |
| Large STL file | Fine mesh | Coarsen mesh for visualization |
| Permission denied | File open elsewhere | Close file first |
\""",
    "skills/docs": \"""
# Abaqus Documentation Reference

## Official Resources
- Abaqus Analysis User's Guide (theory, element formulations)
- Abaqus Scripting User's Guide (Python API)
- Abaqus Scripting Reference Guide (API reference)
- Abaqus Keywords Reference Guide (input file syntax)
- Abaqus Verification Manual (benchmark problems)

## Scripting API Quick Reference
| Module | Purpose |
|--------|---------|
| abaqus | Session and MDB (model database) |
| abaqusConstants | Enum values (STEP, TOTAL, etc.) |
| odbAccess | ODB read/write operations |
| part | Part creation, geometry operations |
| material | Material property definitions |
| section | Section assignment |
| assembly | Assembly and instance management |
| step | Analysis step creation |
| load | Load and BC creation |
| interaction | Contact and constraint creation |
| job | Job submission and monitoring |
| visualization | Viewport and display control |

## Common API Patterns
| Task | Pattern |
|------|---------|
| Create model | mdb.Model(name='Model-1') |
| Create part | model.ConstrainedSketch + Part |
| Create material | model.Material(name='Steel') |
| Create section | model.HomogeneousSolidSection |
| Create step | model.StaticStep |
| Create load | model.ConcentratedForce |
| Create BC | model.EncastreBC |
| Create job | mdb.Job(name='Job-1', model='Model-1') |
| Open ODB | odbAccess.openOdb(path, readOnly=True) |

## Unit System Reference
This MCP uses mm-tonne-s-N-MPa, which is fully consistent:
- 1 N = 1 tonne * 1 mm/s^2
- 1 MPa = 1 N/mm^2
- Density in tonne/mm^3 (steel = 7.85e-9)
- Gravity = 9810 mm/s^2
\""",
}
"""

# Insert new skills before the closing brace
insert_pos = content.rfind("\n}")
if insert_pos == -1:
    insert_pos = content.rfind("}")
    content = content[:insert_pos] + new_skills + "\n" + content[insert_pos:]
else:
    content = content[:insert_pos] + new_skills + "\n" + content[insert_pos:]

# Update the index
old_idx_start = content.find('"skills/index": """')
if old_idx_start >= 0:
    next_skill = content.find('\n    "skills/units"', old_idx_start)
    if next_skill > 0:
        new_index = "\"skills/index\": \"\"\"\n# Abaqus Skills Index\n\n## Modeling\n- abaqus://skills/geometry -- Part creation, sketches, CAD import, sets/surfaces\n- abaqus://skills/material -- Material properties, section assignment, common values\n- abaqus://skills/mesh -- Element types, mesh sizing, quality checks\n- abaqus://skills/interaction -- Contact, tie constraints, coupling, master/slave\n\n## Setup\n- abaqus://skills/step -- Analysis procedures, increment control, nlgeom\n- abaqus://skills/boundary-condition -- BC types, symmetry, rigid body checking\n- abaqus://skills/load -- Forces, pressures, gravity, sign conventions\n- abaqus://skills/output -- Field/history output, variable selection, file size\n- abaqus://skills/amplitude -- Time-varying load profiles, ramps, periodic\n- abaqus://skills/field -- Initial conditions, predefined fields, temperature import\n\n## Execution\n- abaqus://skills/job -- Submission, monitoring, troubleshooting\n- abaqus://skills/export -- STL/STEP/CSV/INP export, geometry and results\n\n## Postprocessing\n- abaqus://skills/odb -- Result extraction, max stress, displacement, reactions\n\n## Analysis Workflows\n- abaqus://skills/static-analysis -- End-to-end static stress analysis\n- abaqus://skills/modal-analysis -- Natural frequency and mode shape extraction\n- abaqus://skills/contact-analysis -- Multi-body contact, friction, tie constraints\n- abaqus://skills/dynamic-analysis -- Impact, crash, transient response (explicit/implicit)\n- abaqus://skills/thermal-analysis -- Heat transfer, conduction, convection, radiation\n- abaqus://skills/fatigue-analysis -- S-N curve, cycle counting, damage accumulation\n- abaqus://skills/coupled-analysis -- Thermal-structural, piezoelectric, acoustic\n\n## Optimization\n- abaqus://skills/optimization -- Tosca setup, design responses, objectives\n- abaqus://skills/topology-optimization -- Material distribution, lightweight design\n- abaqus://skills/shape-optimization -- Surface geometry, stress reduction\n\n## Reference\n- abaqus://skills/units -- Consistent unit system (mm-tonne-s-N-MPa)\n- abaqus://skills/docs -- API reference, common patterns, unit system\n\"\"\",\n"
        content = content[:old_idx_start] + new_index + content[next_skill:]

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Success")