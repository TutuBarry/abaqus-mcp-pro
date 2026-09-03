"""Convergence Advisor: auto-fix suggestions for solver convergence problems.

When the Solver Doctor detects a convergence pattern, the Convergence Advisor
provides specific, actionable parameter adjustments that the AI can apply
via run_python. Each pattern maps to a ranked list of fix suggestions,
prioritized by likelihood of success.

Patterns covered:
- too_many_attempts
- time_increment_too_small
- maximum_increments_exceeded
- negative_eigenvalues
- rigid_body_motion
- contact_overclosure
- excessive_distortion
- explicit_stable_time_too_small
- zero_pivot
- material_instability
- excessive_pivot_ratio
"""

from __future__ import annotations

from dataclasses import dataclass, field
@dataclass
class FixSuggestion:
    """A single auto-fix suggestion."""
    fix_id: str
    description: str
    code_template: str = ""
    priority: int = 3
    risk: str = "medium"
    keywords: list = field(default_factory=list)

    def to_dict(self):
        return {
            "fix_id": self.fix_id,
            "description": self.description,
            "code_template": self.code_template,
            "priority": self.priority,
            "risk": self.risk,
            "keywords": self.keywords,
        }


@dataclass
class ConvergenceAdvice:
    """Collection of fix suggestions for a diagnosed convergence problem."""
    pattern_id: str
    pattern_description: str
    suggestions: list = field(default_factory=list)

    def to_dict(self):
        return {
            "pattern_id": self.pattern_id,
            "pattern_description": self.pattern_description,
            "suggestions": [s.to_dict() for s in self.suggestions],
        }


CONVERGENCE_FIXES = {
    "too_many_attempts": [
        FixSuggestion(
            fix_id="reduce_initial_inc",
            description="Reduce initial increment size (e.g., from 0.01 to 0.001)",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(initialInc=0.001)",
            priority=1, risk="low",
            keywords=["initial", "increment", "inc"],
        ),
        FixSuggestion(
            fix_id="increase_max_inc",
            description="Increase maximum number of increments (e.g., to 1000)",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(maxNumInc=1000)",
            priority=2, risk="low",
            keywords=["maximum", "increments", "max"],
        ),
        FixSuggestion(
            fix_id="enable_line_search",
            description="Enable line search for Newton-Raphson (helps with nonlinearities)",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(lineSearch=ON)",
            priority=2, risk="low",
            keywords=["line", "search"],
        ),
        FixSuggestion(
            fix_id="reduce_min_inc",
            description="Reduce minimum increment size (e.g., from 1e-5 to 1e-8)",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(minInc=1e-8)",
            priority=3, risk="medium",
            keywords=["minimum", "increment", "min"],
        ),
        FixSuggestion(
            fix_id="check_contact",
            description="Check contact pairs for overclosure or sudden stiffness changes",
            priority=3, risk="low",
            keywords=["contact", "overclosure"],
        ),
    ],

    "time_increment_too_small": [
        FixSuggestion(
            fix_id="enable_stabilization",
            description="Enable automatic stabilization with dissipated energy fraction",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(stabilizationMethod=AUTOMATIC_STABILIZATION, stabilizationMagnitude=0.0002)",
            priority=1, risk="low",
            keywords=["stabilization", "automatic"],
        ),
        FixSuggestion(
            fix_id="reduce_min_inc",
            description="Reduce minimum increment size (e.g., from 1e-5 to 1e-10)",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(minInc=1e-10)",
            priority=2, risk="medium",
            keywords=["minimum", "increment", "min"],
        ),
        FixSuggestion(
            fix_id="add_damping",
            description="Add global damping to stabilize local instabilities",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(stabilizationMethod=DAMPING_FACTOR, stabilizationMagnitude=0.0001)",
            priority=2, risk="medium",
            keywords=["damping", "stabilize", "stabilization"],
        ),
        FixSuggestion(
            fix_id="check_local_instability",
            description="Check for local instabilities: buckling, snap-through, or material softening",
            priority=3, risk="low",
            keywords=["buckling", "snap", "instability", "softening"],
        ),
        FixSuggestion(
            fix_id="switch_to_riks",
            description="Switch to Riks analysis for post-buckling or unstable response",
            code_template="# Consider replacing the Static, General step with Static, Riks",
            priority=5, risk="high",
            keywords=["riks", "post-buckling"],
        ),
    ],

    "maximum_increments_exceeded": [
        FixSuggestion(
            fix_id="increase_max_inc",
            description="Increase maximum number of increments (double to 200 minimal, 1000 for tough jobs)",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(maxNumInc=1000)",
            priority=1, risk="low",
            keywords=["maximum", "increments", "max"],
        ),
        FixSuggestion(
            fix_id="increase_initial_inc",
            description="Increase initial increment size to reduce total increments needed",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(initialInc=0.1)",
            priority=2, risk="medium",
            keywords=["initial", "increment", "inc"],
        ),
        FixSuggestion(
            fix_id="check_slow_convergence",
            description="Check if convergence is slow but stable -- the model may be near limit load",
            priority=3, risk="low",
            keywords=["slow", "convergence", "limit"],
        ),
    ],

    "negative_eigenvalues": [
        FixSuggestion(
            fix_id="check_rigid_body",
            description="Check for rigid body motion: ensure all parts are constrained",
            priority=1, risk="low",
            keywords=["rigid", "body", "unconstrained", "bc"],
        ),
        FixSuggestion(
            fix_id="add_stabilization",
            description="Add automatic stabilization to suppress negative eigenvalues",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(stabilizationMethod=AUTOMATIC_STABILIZATION, stabilizationMagnitude=0.0002)",
            priority=2, risk="low",
            keywords=["stabilization", "automatic"],
        ),
        FixSuggestion(
            fix_id="check_material",
            description="Check material properties: negative eigenvalues often indicate unstable material",
            priority=2, risk="low",
            keywords=["material", "unstable", "softening"],
        ),
        FixSuggestion(
            fix_id="check_contact_chatter",
            description="Check for contact chattering: nodes repeatedly opening/closing",
            priority=3, risk="low",
            keywords=["contact", "chattering", "open", "close"],
        ),
        FixSuggestion(
            fix_id="add_weak_springs",
            description="Add weak springs to ground to suppress rigid body modes",
            code_template="# Use: mdb.models['__MODEL__'].rootAssembly.engineeringFeatures.SpringDashpotToGround(...)",
            priority=4, risk="medium",
            keywords=["springs", "ground", "weak"],
        ),
    ],

    "rigid_body_motion": [
        FixSuggestion(
            fix_id="add_bc",
            description="Add boundary conditions to all unconstrained degrees of freedom",
            priority=1, risk="low",
            keywords=["boundary", "condition", "bc", "constrain"],
        ),
        FixSuggestion(
            fix_id="check_disconnected",
            description="Check for disconnected parts: orphan instances not connected to anything",
            priority=1, risk="low",
            keywords=["disconnected", "orphan", "instance"],
        ),
        FixSuggestion(
            fix_id="add_contact",
            description="Add contact interactions between parts that should be connected",
            priority=2, risk="low",
            keywords=["contact", "interaction", "connect"],
        ),
        FixSuggestion(
            fix_id="add_weak_springs",
            description="Add weak springs to ground (e.g., 1e-6 N/mm stiffness) as temporary fix",
            code_template="# Use: mdb.models['__MODEL__'].rootAssembly.engineeringFeatures.SpringDashpotToGround(...)",
            priority=3, risk="medium",
            keywords=["springs", "ground", "weak"],
        ),
        FixSuggestion(
            fix_id="check_tie",
            description="Check tie constraints: tighten position tolerance or refine mesh",
            priority=3, risk="low",
            keywords=["tie", "constraint", "tolerance"],
        ),
    ],

    "contact_overclosure": [
        FixSuggestion(
            fix_id="adjust_tolerance",
            description="Adjust contact pair position tolerance (e.g., from 0.1 to 0.5)",
            code_template="# Adjust in contact pair definition: adjust=0.5",
            priority=1, risk="low",
            keywords=["adjust", "tolerance", "position"],
        ),
        FixSuggestion(
            fix_id="use_adjust_only",
            description="Use adjust= parameter to remove initial overclosure without strain",
            code_template="# In contact pair: specify adjust=<value> to remove overclosure",
            priority=1, risk="low",
            keywords=["adjust", "overclosure"],
        ),
        FixSuggestion(
            fix_id="check_mesh_alignment",
            description="Check mesh alignment between contact surfaces -- refine if needed",
            priority=2, risk="low",
            keywords=["mesh", "alignment", "refine"],
        ),
        FixSuggestion(
            fix_id="use_small_sliding",
            description="Switch to small-sliding contact if relative motion is small",
            code_template="# Set sliding formulation to SMALL in contact pair definition",
            priority=2, risk="medium",
            keywords=["small", "sliding", "finite"],
        ),
        FixSuggestion(
            fix_id="check_interference",
            description="Check for interference fit: use interference fit option if intentional",
            code_template="# In contact pair: interference=ON",
            priority=3, risk="low",
            keywords=["interference", "shrink", "fit"],
        ),
    ],

    "excessive_distortion": [
        FixSuggestion(
            fix_id="reduce_time_inc",
            description="Reduce time increment to avoid large deformation per step",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(initialInc=0.001, maxInc=0.01)",
            priority=1, risk="low",
            keywords=["time", "increment", "reduce"],
        ),
        FixSuggestion(
            fix_id="use_ale",
            description="Use ALE adaptive meshing to maintain element quality during large deformation",
            code_template="# Set up ALE adaptive mesh domain in the step",
            priority=2, risk="medium",
            keywords=["ale", "adaptive", "mesh", "remesh"],
        ),
        FixSuggestion(
            fix_id="use_reduced_integration",
            description="Switch to reduced-integration elements (C3D8R instead of C3D8)",
            code_template="# Change element type to reduced integration variant",
            priority=2, risk="medium",
            keywords=["reduced", "integration", "C3D8R", "hourglass"],
        ),
        FixSuggestion(
            fix_id="add_damage",
            description="Add damage/failure criteria to allow element deletion",
            code_template="# Add ductile damage or shear damage to material definition",
            priority=3, risk="medium",
            keywords=["damage", "failure", "deletion"],
        ),
        FixSuggestion(
            fix_id="remesh_with_finer",
            description="Remesh with finer elements in high-gradient regions",
            priority=3, risk="medium",
            keywords=["remesh", "finer", "refine"],
        ),
    ],

    "explicit_stable_time_too_small": [
        FixSuggestion(
            fix_id="mass_scaling",
            description="Apply mass scaling to increase stable time increment",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(massScaling=((SEMI_AUTOMATIC, MODEL, AT_BEGINNING, 1e-6),))",
            priority=1, risk="low",
            keywords=["mass", "scaling", "stable", "time"],
        ),
        FixSuggestion(
            fix_id="check_smallest_element",
            description="Find and remesh the smallest element(s) that limit the time step",
            priority=1, risk="low",
            keywords=["smallest", "element", "limit", "critical"],
        ),
        FixSuggestion(
            fix_id="reduce_element_count",
            description="Reduce element count by coarsening mesh in non-critical regions",
            priority=2, risk="medium",
            keywords=["coarsen", "mesh", "fewer", "elements"],
        ),
        FixSuggestion(
            fix_id="use_subcycling",
            description="Enable subcycling to allow different time steps for different element groups",
            code_template="# Set subcycling in the explicit step definition",
            priority=3, risk="low",
            keywords=["subcycling", "subcycle"],
        ),
        FixSuggestion(
            fix_id="use_implicit",
            description="Consider switching to implicit analysis if quasi-static",
            priority=4, risk="high",
            keywords=["implicit", "quasi-static", "static"],
        ),
    ],

    "zero_pivot": [
        FixSuggestion(
            fix_id="check_underconstrained",
            description="Check for underconstrained DOFs: add missing boundary conditions",
            priority=1, risk="low",
            keywords=["underconstrained", "dof", "boundary", "bc"],
        ),
        FixSuggestion(
            fix_id="check_mechanism",
            description="Check for mechanism (unstable structure): look for unconnected parts",
            priority=1, risk="low",
            keywords=["mechanism", "unstable", "unconnected"],
        ),
        FixSuggestion(
            fix_id="add_stabilization",
            description="Add stabilization to suppress zero-pivot warnings",
            code_template="mdb.models['__MODEL__'].steps['__STEP__'].setValues(stabilizationMethod=DAMPING_FACTOR, stabilizationMagnitude=1e-6)",
            priority=3, risk="medium",
            keywords=["stabilization", "damping"],
        ),
    ],

    "material_instability": [
        FixSuggestion(
            fix_id="check_material_data",
            description="Verify material data: correct units, plausible values",
            priority=1, risk="low",
            keywords=["material", "data", "units", "verify"],
        ),
        FixSuggestion(
            fix_id="add_hardening",
            description="Add plastic hardening to prevent sudden softening",
            code_template="# Add plastic hardening data to material definition",
            priority=2, risk="low",
            keywords=["hardening", "plastic", "softening"],
        ),
        FixSuggestion(
            fix_id="use_hyperelastic",
            description="Use hyperelastic material for large-strain rubber-like behavior",
            code_template="# Replace Elastic with Hyperelastic material model",
            priority=3, risk="medium",
            keywords=["hyperelastic", "rubber", "large", "strain"],
        ),
        FixSuggestion(
            fix_id="check_damage_initiation",
            description="Check if damage initiation criteria are triggering prematurely",
            priority=3, risk="low",
            keywords=["damage", "initiation", "premature"],
        ),
    ],

    "excessive_pivot_ratio": [
        FixSuggestion(
            fix_id="check_bc",
            description="Check boundary conditions: mixed DOF constraints may cause singularities",
            priority=1, risk="low",
            keywords=["boundary", "condition", "mixed", "singularity"],
        ),
        FixSuggestion(
            fix_id="check_coupling",
            description="Check kinematic couplings: over-constrained nodes",
            priority=2, risk="low",
            keywords=["coupling", "kinematic", "over-constrained"],
        ),
        FixSuggestion(
            fix_id="check_connector",
            description="Check connector elements for duplicate or conflicting definitions",
            priority=2, risk="low",
            keywords=["connector", "duplicate", "conflict"],
        ),
    ],
}


def get_advice_for_pattern(pattern_id):
    """Get fix suggestions for a diagnosed convergence pattern."""
    fixes = CONVERGENCE_FIXES.get(pattern_id)
    if fixes is None:
        return None

    descriptions = {
        "too_many_attempts": "Too many cutback attempts -- the solver is struggling to converge within a single increment",
        "time_increment_too_small": "Time increment required is less than the specified minimum",
        "maximum_increments_exceeded": "Maximum number of increments exceeded -- the job ran out of allowed increments",
        "negative_eigenvalues": "Negative eigenvalues detected -- indicates local or global instability",
        "rigid_body_motion": "Rigid body motion detected -- some parts are not properly constrained",
        "contact_overclosure": "Contact overclosure detected -- nodes are penetrating the master surface",
        "excessive_distortion": "Excessive element distortion -- elements are deforming too much",
        "explicit_stable_time_too_small": "Stable time increment is too small for explicit analysis",
        "zero_pivot": "Zero pivot detected -- stiffness matrix is singular due to missing constraints",
        "material_instability": "Material instability -- material model is producing unstable behavior",
        "excessive_pivot_ratio": "Excessive pivot ratio -- near-singularity in the stiffness matrix",
    }

    return ConvergenceAdvice(
        pattern_id=pattern_id,
        pattern_description=descriptions.get(pattern_id, f"Convergence issue: {pattern_id}"),
        suggestions=list(fixes),
    )


def get_advice_for_patterns(pattern_ids):
    """Get fix suggestions for multiple diagnosed patterns."""
    results = []
    for pid in pattern_ids:
        advice = get_advice_for_pattern(pid)
        if advice is not None:
            results.append(advice)
    return results


def format_convergence_advice_markdown(advice):
    """Render convergence advice as structured Markdown."""
    lines = []
    lines.append(f"###  Auto-Fix Suggestions: `{advice.pattern_id}`")
    lines.append("")
    lines.append(f"> {advice.pattern_description}")
    lines.append("")

    lines.append("| # | Priority | Risk | Suggestion |")
    lines.append("|---|----------|------|------------|")
    for i, s in enumerate(advice.suggestions, 1):
        risk_icon = {"low": " Low", "medium": " Medium", "high": " High"}.get(s.risk, s.risk)
        lines.append(f"| {i} | P{s.priority} | {risk_icon} | {s.description} |")
    lines.append("")

    code_suggestions = [s for s in advice.suggestions if s.code_template]
    if code_suggestions:
        lines.append("#### Code Templates")
        lines.append("")
        for s in code_suggestions:
            lines.append(f"**{s.fix_id}** (P{s.priority}, {s.risk} risk):")
            lines.append("```python")
            lines.append(s.code_template)
            lines.append("```")
            lines.append("")

    lines.append("---")
    lines.append("*Suggestions generated by abaqus-mcp-pro Convergence Advisor.*")
    return "\n".join(lines)


def format_convergence_advice_compact(advice):
    """Compact one-line format for convergence advice."""
    top = advice.suggestions[0] if advice.suggestions else None
    if top:
        return f"[ADVICE] {advice.pattern_id}: {top.description} ({len(advice.suggestions)} suggestions)"
    return f"[ADVICE] {advice.pattern_id}: No suggestions available"


def format_all_advice_markdown(advice_list):
    """Render all convergence advice as a single Markdown section."""
    if not advice_list:
        return ""
    lines = []
    lines.append("##  Convergence Auto-Fix Suggestions")
    lines.append("")
    for advice in advice_list:
        lines.append(format_convergence_advice_markdown(advice))
        lines.append("")
    return "\n".join(lines)


def extract_pattern_ids_from_diagnosis(diagnosis_report):
    """Extract error/warning pattern IDs from a solver diagnosis report dict."""
    events = diagnosis_report.get("events", [])
    if not events:
        return []
    pattern_ids = []
    seen = set()
    for event in events:
        severity = event.get("severity", "info")
        if severity in ("error", "warning"):
            pid = event.get("pattern_id", "")
            if pid and pid not in seen:
                pattern_ids.append(pid)
                seen.add(pid)
    return pattern_ids
