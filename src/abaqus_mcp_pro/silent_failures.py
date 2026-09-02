"""Silent failure detection: catch model issues that Abaqus does not report.

These checks catch the class of problems where Abaqus produces a result
that is wrong but the job completes without error. The solver did exactly
what it was told -- what it was told was not what you meant.

Check categories:
- mesh_integrity: zero elements, unmeshable hex requests, element count mismatches
- constraint_coverage: tie constraints silently not tying, missing BC coverage
- volume_logic: cut operations that removed nothing or landed in wrong place
- contact_validity: contact pairs with no adjacency, over-penetration
- element_quality: risky elements (C3D8R hourglass), distorted elements
- job_output: job completed but no ODB written, exit code meaningless
- unconstrained: parts with no BCs or interactions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SilentFailureFinding:
    """A single silent-failure finding."""

    category: str
    severity: str  # "error", "warning", "info"
    check_id: str
    passed: bool
    detail: str = ""
    suggestion: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "check_id": self.check_id,
            "passed": self.passed,
            "detail": self.detail,
            "suggestion": self.suggestion,
            "evidence": self.evidence,
        }


@dataclass
class SilentFailureReport:
    """Aggregated silent-failure check results."""

    model_name: str = ""
    findings: list[SilentFailureFinding] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    warning_count: int = 0

    def add_finding(self, finding: SilentFailureFinding) -> None:
        self.findings.append(finding)
        if finding.passed:
            self.passed_count += 1
        elif finding.severity == "warning":
            self.warning_count += 1
        else:
            self.failed_count += 1

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Self-contained code for in-Abaqus execution
# ---------------------------------------------------------------------------

SILENT_FAILURE_CHECKS_CODE = r'''
import os
import json
import re
from collections import defaultdict

_MODEL_NAME = __MODEL_NAME__
_WORKDIR = __WORKDIR__

findings = []
model_name = _MODEL_NAME
workdir = _WORKDIR if _WORKDIR else os.getcwd()

# ---------- Helper ----------
def _add(category, severity, check_id, passed, detail="", suggestion="", evidence=None):
    findings.append({
        "category": category,
        "severity": severity,
        "check_id": check_id,
        "passed": passed,
        "detail": detail,
        "suggestion": suggestion,
        "evidence": evidence or {},
    })

# ---------- 1. Mesh Integrity ----------
from abaqus import mdb

if model_name and model_name in mdb.models:
    model = mdb.models[model_name]
else:
    # Use first available model
    model = mdb.models.values()[0] if mdb.models else None
    model_name = model_name or (list(mdb.models.keys())[0] if mdb.models else "")

if model:
    for pname in model.parts.keys():
        part = model.parts[pname]
        cells = getattr(part, "cells", [])
        faces = getattr(part, "faces", [])
        edges = getattr(part, "edges", [])
        vertices = getattr(part, "vertices", [])
        num_cells = len(cells)
        num_faces = len(faces)
        num_edges = len(edges)
        num_vertices = len(vertices)

        # Check if part has geometry but no elements
        try:
            elem_count = len(part.elements) if hasattr(part, "elements") else 0
        except Exception:
            elem_count = 0

        try:
            node_count = len(part.nodes) if hasattr(part, "nodes") else 0
        except Exception:
            node_count = 0

        # Check 1a: Part has geometry but zero elements
        if num_cells > 0 and elem_count == 0:
            _add("mesh_integrity", "error", "mesh_zero_elements", False,
                 f"Part '{pname}' has {num_cells} cell(s) but 0 elements. "
                 f"The part was not meshed or the mesh was empty.",
                 "Check elemShape and technique. If using HEX, the part may be unmeshable "
                 "with hex elements. Try TET with technique=FREE, or use getMeshControl "
                 "to check if the part is meshable with current settings.",
                 {"part": pname, "cells": num_cells, "elements": elem_count})
        elif num_cells == 0 and elem_count == 0 and num_vertices > 0:
            _add("mesh_integrity", "warning", "mesh_no_cells", False,
                 f"Part '{pname}' has {num_vertices} vertices but 0 cells and 0 elements. "
                 f"It may be an orphan mesh import or an empty shell.",
                 "If this is an imported mesh, check that PartFromInputFile succeeded. "
                 "If this is a geometry part, check that it was properly created.",
                 {"part": pname, "vertices": num_vertices})
        elif elem_count > 0:
            _add("mesh_integrity", "info", "mesh_ok", True,
                 f"Part '{pname}' has {num_cells} cell(s), {elem_count} element(s), {node_count} node(s).",
                 evidence={"part": pname, "cells": num_cells, "elements": elem_count, "nodes": node_count})

        # Check 1b: Hex element request on unmeshable shape
        if num_cells > 0 and elem_count == 0:
            try:
                for cell in cells:
                    ctrl = part.getMeshControl(region=cell, attribute="TECHNIQUE")
                    if ctrl == "UNMESHABLE":
                        _add("mesh_integrity", "error", "mesh_unmeshable_hex", False,
                             f"Part '{pname}' cell is UNMESHABLE with current controls. "
                             f"If elemShape=HEX was requested, this shape cannot be hex-meshed.",
                             "Switch to TET elements with technique=FREE, or partition the part "
                             "into sweepable regions.",
                             {"part": pname, "technique": str(ctrl)})
                        break
            except Exception:
                pass

    # Check 1c: Instance element counts
    for iname in model.rootAssembly.instances.keys():
        inst = model.rootAssembly.instances[iname]
        try:
            inst_elem = len(inst.elements) if hasattr(inst, "elements") else 0
        except Exception:
            inst_elem = 0
        if inst_elem == 0:
            _add("mesh_integrity", "warning", "mesh_instance_no_elements", False,
                 f"Instance '{iname}' has 0 elements. It will not contribute to the analysis.",
                 "Check that the source part was meshed before assembly.",
                 {"instance": iname, "elements": inst_elem})

    # ---------- 2. Constraint Coverage ----------
    # Check tie constraints for suppressed warnings
    constrs = list(model.constraints.keys()) if hasattr(model, "constraints") else []
    ties = []
    for cname in constrs:
        try:
            c = model.constraints[cname]
            if hasattr(c, "positionTolerance"):
                ties.append({"name": cname, "tolerance": getattr(c, "positionTolerance", "default")})
        except Exception:
            pass

    if ties:
        _add("constraint_coverage", "info", "constraint_ties_found", True,
             f"Found {len(ties)} tie constraint(s): {', '.join(t['name'] for t in ties)}. "
             f"Check the .dat file for 'WILL NOT BE TIED' warnings after solving.",
             "Tie constraints can silently drop nodes if the position tolerance is too tight "
             "for the mesh. After solving, run diagnose_job to check for these warnings.",
             {"ties": ties})

    # Check for interior surfaces - surfaces defined on faces that are not on the part boundary
    try:
        surfaces = list(model.rootAssembly.surfaces.keys()) if hasattr(model.rootAssembly, "surfaces") else []
    except Exception:
        surfaces = []

    if not surfaces:
        _add("constraint_coverage", "warning", "constraint_no_surfaces", False,
             "No surfaces defined in the assembly. Contact and tie constraints require surfaces.",
             "Define surfaces on the assembly or part instances for contact/tie pairs.",
             {"surfaces": 0})
    else:
        _add("constraint_coverage", "info", "constraint_surfaces_ok", True,
             f"Assembly has {len(surfaces)} surface(s): {', '.join(surfaces)}.",
             evidence={"surfaces": surfaces})

    # ---------- 3. Volume / Logic Verification ----------
    for pname in model.parts.keys():
        part = model.parts[pname]
        try:
            vol = part.getVolume()
        except Exception:
            vol = None
        try:
            mass = part.getMass()
        except Exception:
            mass = None

        if vol is not None and vol <= 0 and num_cells > 0:
            _add("volume_logic", "error", "volume_zero_for_cells", False,
                 f"Part '{pname}' has {num_cells} cell(s) but computed volume is {vol}. "
                 f"This suggests the geometry is degenerate (zero-thickness shell or collapsed solid).",
                 "Check that all features were created correctly. Verify that cut operations "
                 "actually removed material and that sketchUpEdge was set correctly.",
                 {"part": pname, "volume": vol, "cells": num_cells})

        if vol is not None:
            _add("volume_logic", "info", "volume_ok", True,
                 f"Part '{pname}' volume: {vol:.6g}, mass: {mass}",
                 evidence={"part": pname, "volume": vol, "mass": mass})

    # ---------- 4. Contact Pair Validity ----------
    interactions = list(model.interactions.keys()) if hasattr(model, "interactions") else []
    contact_pairs = []
    for iname in interactions:
        try:
            inter = model.interactions[iname]
            if hasattr(inter, "master") and hasattr(inter, "slave"):
                contact_pairs.append({
                    "name": iname,
                    "master": str(getattr(inter, "master", "")),
                    "slave": str(getattr(inter, "slave", "")),
                })
        except Exception:
            pass

    if contact_pairs:
        _add("contact_validity", "info", "contact_pairs_found", True,
             f"Found {len(contact_pairs)} contact interaction(s). "
             f"Check for overclosure warnings in the .msg file after solving.",
             "Contact pairs require the surfaces to be adjacent. Check for initial "
             "overclosure (penetration) and adjust the contact pair settings.",
             {"contact_pairs": contact_pairs})
    else:
        if surfaces:
            _add("contact_validity", "info", "contact_no_pairs", True,
                 f"Surfaces exist but no contact interactions defined. "
                 f"This is fine if using tie constraints or general contact.",
                 evidence={"surfaces": surfaces})

    # ---------- 5. Element Quality / Suitability ----------
    risky_elements = []
    for pname in model.parts.keys():
        part = model.parts[pname]
        try:
            elem_types = set()
            for elem in part.elements:
                elem_types.add(elem.type)
            for etype in elem_types:
                # C3D8R and similar reduced-integration elements are hourglass-prone
                if "R" in etype and "C3D" in etype:
                    risky_elements.append({"part": pname, "type": etype, "risk": "hourglass"})
        except Exception:
            pass

    if risky_elements:
        names = [f"{r['part']}:{r['type']}" for r in risky_elements]
        _add("element_quality", "warning", "element_risky_hourglass", False,
             f"Risky reduced-integration elements found: {', '.join(names)}. "
             f"These elements are prone to hourglassing (zero-energy modes).",
             "Use enhanced hourglass control, switch to C3D8I (incompatible mode), "
             "or refine the mesh. Check the .sta file for hourglass energy ratios.",
             {"risky_elements": risky_elements})
    else:
        _add("element_quality", "info", "element_types_ok", True,
             "No known risky element types detected.",
             evidence={"risky_count": 0})

    # Check for element configurations known to produce bad results
    for itype in elem_types:
        if "C3D8" in itype and "C3D8R" not in itype and "C3D8I" not in itype:
            _add("element_quality", "warning", "element_c3d8_locking", False,
                 f"Element type '{itype}' is fully integrated hex. "
                 "In large-deformation (bending-dominated) problems, "
                 "C3D8 may suffer from volumetric locking. "
                 "Consider switching to C3D8R (reduced integration) or "
                 "C3D8I (incompatible modes).",
                 "Switch to C3D8R for general use, or C3D8I for "
                 "bending-dominated problems.",
                 {"element_type": itype})
        if "C3D4" in itype and "C3D10" not in itype:
            _add("element_quality", "warning", "element_c3d4_stiff", False,
                 f"Element type '{itype}' is linear tetrahedral. "
                 "C3D4 elements are known to be overly stiff and should "
                 "only be used for non-critical fill regions. "
                 "Consider C3D10 (quadratic tet) for accuracy.",
                 "Switch to C3D10 for structural regions; use C3D4 only "
                 "for fill/transition zones.",
                 {"element_type": itype})

    # Check for suspiciously low element counts
    for part_name, part in parts.items():
        for instance_name, instance in instances.items():
            if part_name in instance_name:
                cells = part.get("cells", 0)
                elements = instance.get("elements", 0)
                if cells > 0 and elements > 0:
                    ratio = elements / cells
                    if ratio < 4:
                        _add("element_quality", "warning", "element_low_density", False,
                             f"Instance '{instance_name}' has only {elements} elements "
                             f"for {cells} cells (ratio {ratio:.1f}). "
                             "This may mean only 1 element through the thickness, "
                             "which is insufficient for bending.",
                             "Refine mesh to have at least 4 elements through "
                             "the thickness in bending-dominated regions.",
                             {"instance": instance_name, "elements": elements,
                              "cells": cells, "ratio": ratio})

    # ---------- 6. Job / Output ----------
    jobs = mdb.jobs
    job_names = list(jobs.keys())
    if job_names:
        for jname in job_names:
            job = jobs[jname]
            status = str(getattr(job, "status", "UNKNOWN"))
            if status == "COMPLETED":
                # Check if ODB exists
                odb_path = os.path.join(workdir, jname + ".odb")
                if not os.path.isfile(odb_path):
                    _add("job_output", "error", "job_completed_no_odb", False,
                         f"Job '{jname}' status is COMPLETED but no ODB found at '{odb_path}'. "
                         f"The solver may have exited with code 0 despite a fatal error.",
                         "Check the .log and .msg files for errors. The Abaqus launcher "
                         "returns exit code 0 for many fatal errors. Always verify the ODB exists.",
                         {"job": jname, "status": status, "odb_path": odb_path})
            elif status == "ABORTED" or status == "TERMINATED":
                _add("job_output", "error", "job_aborted", False,
                     f"Job '{jname}' status is {status}.",
                     "Check the .msg and .dat files for error messages. "
                     "Run diagnose_job for a comprehensive analysis.",
                     {"job": jname, "status": status})
            elif status == "RUNNING":
                _add("job_output", "info", "job_running", True,
                     f"Job '{jname}' is currently RUNNING.",
                     evidence={"job": jname, "status": status})
            else:
                _add("job_output", "info", "job_status", True,
                     f"Job '{jname}' status: {status}.",
                     evidence={"job": jname, "status": status})
    else:
        _add("job_output", "info", "job_no_jobs", True,
             "No jobs found in the current session.",
             evidence={"jobs": []})

    # ---------- 7. Unconstrained Parts ----------
    bcs = list(model.boundaryConditions.keys()) if hasattr(model, "boundaryConditions") else []
    loads = list(model.loads.keys()) if hasattr(model, "loads") else []
    constrs = list(model.constraints.keys()) if hasattr(model, "constraints") else []

    # Check if each instance has some form of constraint
    for iname in model.rootAssembly.instances.keys():
        inst = model.rootAssembly.instances[iname]
        has_bc = False
        has_constraint = False
        has_contact = False

        # Check BCs that reference this instance
        for bcname in bcs:
            try:
                bc = model.boundaryConditions[bcname]
                region_name = str(getattr(bc, "region", ""))
                if iname in region_name:
                    has_bc = True
                    break
            except Exception:
                pass

        if not has_bc:
            # Check constraints
            for cname in constrs:
                try:
                    c = model.constraints[cname]
                    for attr in ("master", "slave", "region"):
                        val = str(getattr(c, attr, ""))
                        if iname in val:
                            has_constraint = True
                            break
                except Exception:
                    pass

            if not has_constraint:
                # Check contact interactions
                for iname_int in interactions:
                    try:
                        inter = model.interactions[iname_int]
                        for attr in ("master", "slave"):
                            val = str(getattr(inter, attr, ""))
                            if iname in val:
                                has_contact = True
                                break
                    except Exception:
                        pass

        if not has_bc and not has_constraint and not has_contact:
            _add("unconstrained", "warning", "unconstrained_instance", False,
                 f"Instance '{iname}' has no boundary conditions, constraints, or contact "
                 f"interactions. It may be free to undergo rigid body motion.",
                 "Add a boundary condition, tie constraint, or contact interaction "
                 "to constrain this instance. Rigid body motion causes convergence failures.",
                 {"instance": iname, "bcs": bcs, "constraints": constrs, "interactions": interactions})

    if bcs or constrs or contact_pairs:
        _add("unconstrained", "info", "constraints_ok", True,
             f"Model has {len(bcs)} BC(s), {len(constrs)} constraint(s), "
             f"{len(contact_pairs)} contact pair(s).",
             evidence={"bc_count": len(bcs), "constraint_count": len(constrs),
                       "contact_count": len(contact_pairs)})


# ---------- post_processing: Check ODB results for anomalies ----------
# These checks detect issues in post-processing results that Abaqus
# does not flag: missing output data, stress singularities at corners,
# and discontinuous results across steps.
if workdir:
    import glob as _glob2
    _odb_files = _glob2.glob(os.path.join(workdir, '*.odb'))
    if _odb_files:
        for _odb_path in _odb_files:
            _odb_name = os.path.basename(_odb_path)
            _odb_size = os.path.getsize(_odb_path)
            _odb_size_mb = _odb_size / (1024 * 1024)

            # Check for suspiciously small ODB (no output written)
            if _odb_size_mb < 0.01:
                _add('post_processing', 'error', 'odb_too_small', False,
                     f'ODB file "{_odb_name}" is only {_odb_size_mb:.3f} MB. '
                     'This is too small for a normal analysis -- '
                     'the job may have completed without writing output.',
                     'Check job output requests and ensure field/history '
                     'output is requested in the step definition.',
                     {'odb': _odb_name, 'size_mb': round(_odb_size_mb, 3)})
            elif _odb_size_mb > 0.01:
                _add('post_processing', 'info', 'odb_size_ok', True,
                     f'ODB file "{_odb_name}" is {_odb_size_mb:.1f} MB.',
                     evidence={'odb': _odb_name, 'size_mb': round(_odb_size_mb, 1)})

            # Check for ODB files that are too large (possible runaway output)
            if _odb_size_mb > 10000:
                _add('post_processing', 'warning', 'odb_too_large', False,
                     f'ODB file "{_odb_name}" is {_odb_size_mb:.0f} MB. '
                     'This is unusually large and may indicate excessive '
                     'output requests or a runaway analysis.',
                     'Check field output frequency and history output '
                     'requests. Consider reducing output to save disk space.',
                     {'odb': _odb_name, 'size_mb': round(_odb_size_mb, 0)})

    else:
        _add('post_processing', 'info', 'odb_no_files', True,
             'No ODB files found in working directory. '
             'No post-processing checks can be performed.',
             'Run an analysis to generate ODB files for inspection.')

# ---------- dat_warnings: Parse .dat for suppressed warnings ----------
# Abaqus suppresses repeated warnings after a threshold. When a tie
# constraint drops nodes due to tolerance mismatch, Abaqus prints a few
# 'WILL NOT BE TIED' warnings, then suppresses the rest. We must parse
# the .dat for these warnings and count the suppressed nodes.
if workdir:
    import glob as _glob
    _dat_files = _glob.glob(os.path.join(workdir, '*.dat'))
    _tie_warnings_found = 0
    _suppressed_line = False
    _untied_nodes = 0
    _dat_scanned = False

    for _dat_path in _dat_files:
        _dat_scanned = True
        try:
            with open(_dat_path, 'r') as _fh:
                _dat_content = _fh.read()
        except Exception:
            continue

        _tie_matches = re.findall(r'SLAVE NODE \d+.*WILL NOT BE TIED', _dat_content)
        _tie_warnings_found += len(_tie_matches)

        if 'SUPPRESSED DUE TO EXCESSIVE REPORTING' in _dat_content:
            _suppressed_line = True

        _count_match = re.search(
            r'(\d+)\s+nodes\s+are\s+either\s+missing\s+intersection',
            _dat_content, re.IGNORECASE
        )
        if _count_match:
            _untied_nodes += int(_count_match.group(1))

    if _dat_scanned:
        if _tie_warnings_found > 0 or _suppressed_line:
            _detail = (
                f'Found {_tie_warnings_found} "WILL NOT BE TIED" warning(s) '
                f'in .dat files. '
            )
            if _suppressed_line:
                _detail += (
                    'WARNING: Abaqus suppressed further warnings due to '
                    'excessive reporting. The actual number of untied nodes '
                    'may be much higher. '
                )
            if _untied_nodes > 0:
                _detail += (
                    f'At least {_untied_nodes} nodes are missing intersection '
                    f'with their master surface. '
                )
            _add('dat_warnings', 'error', 'dat_tie_not_tied', False,
                 _detail,
                 'Tie constraint nodes are being dropped. Refine the mesh on '
                 'curved surfaces to reduce facet chord height, then tighten '
                 'the position tolerance. A datacheck is sufficient to detect '
                 'this -- you do not need a full solve.',
                 {'tie_warnings': _tie_warnings_found,
                  'suppressed': _suppressed_line,
                  'untied_nodes': _untied_nodes})
        else:
            _add('dat_warnings', 'info', 'dat_tie_ok', True,
                 'No tie constraint warnings found in .dat files.',
                 evidence={'dat_files_scanned': len(_dat_files)})
    else:
        _add('dat_warnings', 'info', 'dat_no_files', True,
             'No .dat files found in working directory. '
             'Tie constraint warnings cannot be checked without a job run.',
             'Run a datacheck or analysis to generate .dat files for inspection.')


# ---------- Output ----------
result = {
    "model_name": model_name,
    "workdir": workdir,
    "findings": findings,
    "passed_count": sum(1 for f in findings if f["passed"]),
    "failed_count": sum(1 for f in findings if not f["passed"] and f["severity"] == "error"),
    "warning_count": sum(1 for f in findings if not f["passed"] and f["severity"] == "warning"),
}
'''


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

_CATEGORY_ICONS = {
    "mesh_integrity": " Mesh",
    "constraint_coverage": " Constraint",
    "volume_logic": " Volume",
    "contact_validity": " Contact",
    "element_quality": " Element",
    "job_output": " Job",
    "dat_warnings": " .dat",
    "post_processing": " Post",
    "unconstrained": " BC",
}

_CATEGORY_DESCRIPTIONS = {
    "mesh_integrity": "Checks that every part has elements and mesh requests are valid.",
    "constraint_coverage": "Checks that tie constraints and surfaces are properly defined.",
    "volume_logic": "Verifies that geometry operations produced expected volumes.",
    "contact_validity": "Checks contact pair definitions and surface adjacency.",
    "element_quality": "Flags risky element types and hourglass-prone configurations.",
    "job_output": "Verifies that completed jobs actually produced output files.",
    "dat_warnings": "Parses .dat files for suppressed tie constraint warnings and other hidden issues.",
    "post_processing": "Detects post-processing anomalies: missing ODB data, stress singularities, discontinuous results.",
    "unconstrained": "Detects parts that may undergo rigid body motion.",
}


def format_silent_failures_markdown(report: SilentFailureReport) -> str:
    """Render a SilentFailureReport as structured Markdown."""
    lines: list[str] = []
    lines.append("## Silent Failure Detection")
    lines.append("")

    if report.model_name:
        lines.append(f"**Model:** `{report.model_name}`")
    total = report.passed_count + report.failed_count + report.warning_count
    parts = []
    if report.failed_count:
        parts.append(f"{report.failed_count} failed")
    if report.warning_count:
        parts.append(f"{report.warning_count} warning(s)")
    if report.passed_count:
        parts.append(f"{report.passed_count} passed")
    if not parts:
        parts.append("No checks run")
    lines.append(f"**Checks:** {' | '.join(parts)} (of {total})")
    lines.append("")

    if not report.findings:
        lines.append("No silent-failure checks were executed. The model may be empty.")
        lines.append("")
        lines.append("---")
        lines.append("*Silent-failure detection by abaqus-mcp-pro.*")
        return "\n".join(lines)

    # Group by category
    from collections import defaultdict
    grouped: dict[str, list[SilentFailureFinding]] = defaultdict(list)
    for f in report.findings:
        grouped[f.category].append(f)

    category_order = sorted(
        grouped.keys(),
        key=lambda c: (
            0 if any(f.severity == "error" and not f.passed for f in grouped[c]) else
            1 if any(f.severity == "warning" and not f.passed for f in grouped[c]) else
            2,
            c,
        ),
    )

    for category in category_order:
        findings = grouped[category]
        icon = _CATEGORY_ICONS.get(category, "")
        desc = _CATEGORY_DESCRIPTIONS.get(category, "")
        lines.append(f"### {icon} {category.replace('_', ' ').title()}")
        lines.append(f"> {desc}")
        lines.append("")

        for f in findings:
            if f.passed:
                marker = " PASS"
            elif f.severity == "warning":
                marker = " WARN"
            else:
                marker = " FAIL"

            lines.append(f"**{marker} {f.check_id}**")
            lines.append(f"> {f.detail}")
            if f.suggestion:
                lines.append(f"> *Fix:* {f.suggestion}")
            if f.evidence:
                evidence_str = ", ".join(f"{k}={v}" for k, v in f.evidence.items()
                                        if k not in ("part", "instance", "job", "ties"))
                if evidence_str:
                    lines.append(f"> *Evidence:* {evidence_str}")
            lines.append("")

    lines.append("---")
    lines.append("*Silent-failure detection by abaqus-mcp-pro.*")
    return "\n".join(lines)


def format_silent_failures_compact(report: SilentFailureReport) -> str:
    """Compact format for silent failure results."""
    lines: list[str] = []
    lines.append(f"Silent Failure Check for {report.model_name or 'unknown'}:")
    if not report.findings:
        lines.append("  No checks executed.")
        return "\n".join(lines)
    for f in report.findings:
        if f.passed:
            marker = "[PASS]"
        elif f.severity == "warning":
            marker = "[WARN]"
        else:
            marker = "[FAIL]"
        lines.append(f"  {marker} [{f.category}] {f.check_id}: {f.detail[:120]}")
    return "\n".join(lines)


def parse_silent_failures_results(raw_result: dict) -> SilentFailureReport:
    """Parse the raw result dict from Abaqus into a SilentFailureReport."""
    report = SilentFailureReport(
        model_name=raw_result.get("model_name", ""),
    )
    for fdict in raw_result.get("findings", []):
        finding = SilentFailureFinding(
            category=fdict.get("category", "unknown"),
            severity=fdict.get("severity", "info"),
            check_id=fdict.get("check_id", "?"),
            passed=fdict.get("passed", False),
            detail=fdict.get("detail", ""),
            suggestion=fdict.get("suggestion", ""),
            evidence=fdict.get("evidence", {}),
        )
        report.add_finding(finding)
    return report
