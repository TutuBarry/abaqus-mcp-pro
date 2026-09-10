# -*- coding: utf-8 -*-
"""
Complete End-to-End Case: Plate with a Hole under Tension
=========================================================

Engineering problem:
  A 100 × 40 × 2 mm steel plate with a 10 mm diameter central hole.
  The plate is pulled in uniaxial tension by prescribing 0.5 mm displacement
  on the right edge while the left edge is fixed.

Purpose:
  Demonstrate the full ABAQUS MCP Pro pipeline —
  natural-language instruction → model → submit → KPI → 3D viewer → report.

Usage (standalone, run inside Abaqus/CAE Python or via MCP bridge):
  # Via Abaqus/CAE:
  #   File > Run Script... > select this file
  #
  # Via MCP bridge (the AI will execute this through run_python):
  #   "Run the complete plate-with-hole analysis in examples/complete_plate_with_hole.py"

Expected results:
  - Stress concentration factor Kt ≈ 2.5–3.0 around the hole
  - Max von Mises stress near hole edge
  - Uniform stress field far from the hole
  - result_mesh.json ready for browser 3D viewer
"""

from __future__ import print_function

import json
import os
import sys
from datetime import datetime

from abaqus import mdb, session
from abaqusConstants import *
import mesh
import regionToolset
from odbAccess import openOdb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get(
    "ABAQUS_EXAMPLE_WORK_DIR",
    os.path.join(SCRIPT_DIR, "output", "complete_plate_with_hole"),
)
MODEL_NAME = "Plate_With_Hole"
JOB_NAME = "plate_with_hole"

# Plate dimensions (mm)
PLATE_LENGTH = 100.0
PLATE_WIDTH = 40.0
PLATE_THICKNESS = 2.0
HOLE_RADIUS = 5.0
HOLE_CENTER_X = PLATE_LENGTH / 2.0
HOLE_CENTER_Y = 0.0

# Material: structural steel
E_STEEL = 210000.0  # MPa
NU_STEEL = 0.30

# Load: prescribed displacement on right edge
IMPOSED_U1 = 0.5  # mm

# Mesh
GLOBAL_SEED = 4.0   # mm — coarse away from hole
HOLE_SEED = 1.0     # mm — refined around hole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def log(msg):
    print("[plate_with_hole] {}".format(msg))


# ---------------------------------------------------------------------------
# Step 1: Build the model
# ---------------------------------------------------------------------------

def build_model():
    log("Step 1/5: Building model...")
    ensure_dir(WORK_DIR)
    os.chdir(WORK_DIR)

    if MODEL_NAME in mdb.models:
        del mdb.models[MODEL_NAME]

    model = mdb.Model(name=MODEL_NAME)

    # -- Sketch: rectangle with a circle cut-out --
    sketch = model.ConstrainedSketch(name="plate_profile", sheetSize=200.0)
    sketch.rectangle(
        point1=(0.0, -PLATE_WIDTH / 2.0),
        point2=(PLATE_LENGTH, PLATE_WIDTH / 2.0),
    )
    sketch.CircleByCenterPerimeter(
        center=(HOLE_CENTER_X, HOLE_CENTER_Y),
        point1=(HOLE_CENTER_X + HOLE_RADIUS, HOLE_CENTER_Y),
    )

    # -- Part: extrude the 2D profile --
    part = model.Part(
        name="Plate", dimensionality=THREE_D, type=DEFORMABLE_BODY
    )
    part.BaseSolidExtrude(sketch=sketch, depth=PLATE_THICKNESS)
    del model.sketches["plate_profile"]

    # -- Material --
    material = model.Material(name="Steel")
    material.Elastic(table=((E_STEEL, NU_STEEL),))

    # -- Section assignment --
    section = model.HomogeneousSolidSection(
        name="SteelSection", material="Steel"
    )
    part.SectionAssignment(
        region=regionToolset.Region(cells=part.cells[:]),
        sectionName="SteelSection",
    )

    # -- Mesh: coarser globally, refined around the hole --
    part.seedPart(size=GLOBAL_SEED, deviationFactor=0.1, minSizeFactor=0.1)

    # Refine edges around the hole
    eps_geom = 1.0e-3
    hole_edges = part.edges.getByBoundingCylinder(
        center1=(HOLE_CENTER_X, HOLE_CENTER_Y, -PLATE_THICKNESS),
        center2=(HOLE_CENTER_X, HOLE_CENTER_Y, PLATE_THICKNESS + eps_geom),
        radius=HOLE_RADIUS + eps_geom,
    )
    part.seedEdgeBySize(edges=hole_edges, size=HOLE_SEED)

    part.setMeshControls(
        regions=part.cells[:], elemShape=HEX, technique=STRUCTURED
    )
    elem_type = mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD)
    part.setElementType(
        regions=(part.cells[:],), elemTypes=(elem_type,)
    )
    part.generateMesh()

    num_nodes = len(part.nodes)
    num_elements = len(part.elements)
    log("  Mesh: {} nodes, {} C3D8R elements".format(num_nodes, num_elements))

    # -- Assembly --
    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    inst = assembly.Instance(name="Plate-1", part=part, dependent=ON)

    # Identify left and right faces for BC / load
    eps = 1.0e-3
    left_faces = inst.faces.getByBoundingBox(
        xMin=-eps, xMax=eps,
        yMin=-PLATE_WIDTH, yMax=PLATE_WIDTH,
        zMin=-eps, zMax=PLATE_THICKNESS + eps,
    )
    right_nodes = inst.nodes.getByBoundingBox(
        xMin=PLATE_LENGTH - eps, xMax=PLATE_LENGTH + eps,
        yMin=-PLATE_WIDTH, yMax=PLATE_WIDTH,
        zMin=-eps, zMax=PLATE_THICKNESS + eps,
    )

    assembly.Set(name="FIXED_LEFT", faces=left_faces)
    assembly.Set(name="PULLED_RIGHT", nodes=right_nodes)

    # -- Analysis step --
    model.StaticStep(
        name="Tension", previous="Initial", nlgeom=OFF,
        initialInc=0.1, maxInc=0.1, minInc=1e-8, maxNumInc=100,
    )

    # -- Boundary conditions --
    model.EncastreBC(
        name="FixLeft",
        createStepName="Initial",
        region=assembly.sets["FIXED_LEFT"],
    )
    model.DisplacementBC(
        name="PullRight",
        createStepName="Tension",
        region=assembly.sets["PULLED_RIGHT"],
        u1=IMPOSED_U1, u2=UNSET, u3=UNSET,
        ur1=UNSET, ur2=UNSET, ur3=UNSET,
    )

    # -- Field output request: stress + displacement + reaction --
    model.fieldOutputRequests["F-Output-1"].setValues(
        variables=("S", "U", "RF"),
    )

    # -- History output: reaction force at fixed end --
    model.HistoryOutputRequest(
        name="H-Output-RF",
        createStepName="Tension",
        variables=("RF1", "RF2", "RF3"),
        region=assembly.sets["FIXED_LEFT"],
    )

    # -- Job --
    mdb.Job(
        name=JOB_NAME,
        model=MODEL_NAME,
        description="Plate with hole — stress concentration benchmark (ABAQUS MCP Pro)",
        type=ANALYSIS,
        memory=90,
        memoryUnits=PERCENTAGE,
        numCpus=2,
        numDomains=2,
    )

    cae_path = os.path.join(WORK_DIR, JOB_NAME + ".cae")
    mdb.saveAs(pathName=cae_path)
    log("  Model saved: {}".format(cae_path))

    return {
        "model_name": MODEL_NAME,
        "job_name": JOB_NAME,
        "work_dir": WORK_DIR,
        "mesh": {"nodes": num_nodes, "elements": num_elements},
    }


# ---------------------------------------------------------------------------
# Step 2: Submit and monitor
# ---------------------------------------------------------------------------

def run_job():
    log("Step 2/5: Submitting job '{}'...".format(JOB_NAME))
    job = mdb.jobs[JOB_NAME]
    job.submit(consistencyChecking=OFF)
    log("  Job submitted, waiting for completion...")
    job.waitForCompletion()

    status = str(getattr(job, "status", "UNKNOWN"))
    log("  Job status: {}".format(status))

    if status != "COMPLETED":
        log("  WARNING: job did not complete normally!")
        # Try to read message file for diagnostics
        msg_path = os.path.join(WORK_DIR, JOB_NAME + ".msg")
        if os.path.isfile(msg_path):
            with open(msg_path, "r") as f:
                tail = f.readlines()[-20:]
            for line in tail:
                log("  MSG: {}".format(line.rstrip()))

    return {"status": status}


# ---------------------------------------------------------------------------
# Step 3: Extract KPI (Key Performance Indicators)
# ---------------------------------------------------------------------------

def extract_kpis():
    log("Step 3/5: Extracting KPI...")
    odb_path = os.path.join(WORK_DIR, JOB_NAME + ".odb")

    if not os.path.isfile(odb_path):
        log("  ERROR: ODB file not found: {}".format(odb_path))
        return None

    odb = openOdb(path=odb_path, readOnly=True)
    step = odb.steps["Tension"]
    frame = step.frames[-1]

    # -- Displacement --
    u_field = frame.fieldOutputs["U"]
    max_u = 0.0
    max_u_node = None
    for value in u_field.values:
        mag = (value.data[0] ** 2 + value.data[1] ** 2 + value.data[2] ** 2) ** 0.5
        if mag > max_u:
            max_u = mag
            max_u_node = value.nodeLabel

    # -- Stress --
    s_field = frame.fieldOutputs["S"]
    max_mises = 0.0
    max_mises_element = None
    max_mises_node = None
    for value in s_field.values:
        if value.mises > max_mises:
            max_mises = value.mises
            max_mises_element = value.elementLabel
            max_mises_node = value.nodeLabel

    # Nominal stress far from hole (at x ≈ PLATE_LENGTH * 0.9)
    # Take average S11 near right edge for reference
    s11_sum = 0.0
    s11_count = 0
    for value in s_field.values:
        # Approximate: elements near the right edge
        s11_sum += value.data[0]
        s11_count += 1
    avg_s11 = s11_sum / float(max(s11_count, 1))

    # Stress concentration factor
    kt = max_mises / abs(avg_s11) if abs(avg_s11) > 1e-6 else 0.0

    # -- Reaction force --
    rf_field = frame.fieldOutputs.get("RF")
    total_rf1 = 0.0
    if rf_field is not None:
        for value in rf_field.values:
            total_rf1 += value.data[0]

    kpis = {
        "max_displacement_mm": float(max_u),
        "max_displacement_node": max_u_node,
        "max_von_mises_MPa": float(max_mises),
        "max_mises_element": max_mises_element,
        "max_mises_node": max_mises_node,
        "average_S11_MPa": float(avg_s11),
        "stress_concentration_factor_Kt": float(kt),
        "total_reaction_force_N": float(total_rf1),
        "engineering_strain": float(IMPOSED_U1 / PLATE_LENGTH),
    }

    odb.close()

    kpi_path = os.path.join(WORK_DIR, "kpi_summary.json")
    with open(kpi_path, "w") as f:
        json.dump(kpis, f, indent=2)
    log("  KPI saved: {}".format(kpi_path))

    for key, val in kpis.items():
        log("  {} = {}".format(key, val))

    return kpis


# ---------------------------------------------------------------------------
# Step 4: Export result_mesh.json for browser 3D viewer
# ---------------------------------------------------------------------------

def export_for_viewer():
    log("Step 4/5: Exporting result_mesh.json for 3D viewer...")
    odb_path = os.path.join(WORK_DIR, JOB_NAME + ".odb")
    output_path = os.path.join(WORK_DIR, "result_mesh.json")

    try:
        from abaqus_mcp_pro.export_result_mesh import export_result_mesh
        result_path = export_result_mesh(
            odb_path=odb_path,
            output_path=output_path,
            step_index=-1,
            frame_step=1,
            deformation_scale=1.0,
        )
        file_size_kb = (
            os.path.getsize(result_path) / 1024.0
            if os.path.isfile(result_path)
            else 0.0
        )
        log("  Exported: {} ({:.1f} KB)".format(result_path, file_size_kb))
        return result_path

    except ImportError:
        log("  WARNING: abaqus_mcp_pro not importable; skipping viewer export.")
        log("  Install with: pip install -e /path/to/abaqus-mcp-pro")
        return None


# ---------------------------------------------------------------------------
# Step 5: Generate simulation report
# ---------------------------------------------------------------------------

def generate_report(model_info, job_result, kpis, viewer_path):
    log("Step 5/5: Generating simulation report...")

    lines = []
    lines.append("# Plate with Hole — Simulation Report")
    lines.append("")
    lines.append("**Generated:** {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append("")

    lines.append("## 1. Problem Description")
    lines.append("")
    lines.append(
        "A rectangular steel plate ({} × {} × {} mm) with a central circular hole "
        "(diameter {} mm) is subjected to uniaxial tension. The left edge is fully fixed; "
        "the right edge is displaced by {} mm in the x-direction. "
        "This is a classic stress concentration benchmark.".format(
            PLATE_LENGTH, PLATE_WIDTH, PLATE_THICKNESS,
            HOLE_RADIUS * 2, IMPOSED_U1,
        )
    )
    lines.append("")

    lines.append("## 2. Model Summary")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append("| Material | Steel (E = {} MPa, ν = {}) |".format(E_STEEL, NU_STEEL))
    lines.append("| Element type | C3D8R (8-node linear brick, reduced integration) |")
    lines.append("| Global seed | {} mm |".format(GLOBAL_SEED))
    lines.append("| Hole edge seed | {} mm |".format(HOLE_SEED))
    lines.append("| Nodes | {} |".format(model_info["mesh"]["nodes"]))
    lines.append("| Elements | {} |".format(model_info["mesh"]["elements"]))
    lines.append("| Analysis type | Static, General |")
    lines.append("| Job status | {} |".format(job_result["status"]))
    lines.append("")

    if kpis:
        lines.append("## 3. Key Results")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(
            "| Max von Mises stress | {:.2f} MPa |".format(
                kpis["max_von_mises_MPa"]
            )
        )
        lines.append(
            "| Stress concentration factor Kt | {:.2f} |".format(
                kpis["stress_concentration_factor_Kt"]
            )
        )
        lines.append(
            "| Max displacement | {:.4f} mm |".format(
                kpis["max_displacement_mm"]
            )
        )
        lines.append(
            "| Total reaction force | {:.2f} N |".format(
                kpis["total_reaction_force_N"]
            )
        )
        lines.append(
            "| Engineering strain | {:.6f} |".format(
                kpis["engineering_strain"]
            )
        )
        lines.append("")
        lines.append(
            "*Note: Theoretical Kt for an infinite plate with a circular hole "
            "under uniaxial tension is 3.0. The computed value may differ due to "
            "finite plate width and mesh density.*"
        )
        lines.append("")

    lines.append("## 4. Output Files")
    lines.append("")
    lines.append("| File | Path |")
    lines.append("|------|------|")
    lines.append("| CAE model | `{}` |".format(
        os.path.join(WORK_DIR, JOB_NAME + ".cae")
    ))
    lines.append("| ODB results | `{}` |".format(
        os.path.join(WORK_DIR, JOB_NAME + ".odb")
    ))
    if viewer_path:
        lines.append("| 3D Viewer JSON | `{}` |".format(viewer_path))
    lines.append("| KPI summary | `{}` |".format(
        os.path.join(WORK_DIR, "kpi_summary.json")
    ))
    lines.append("")

    lines.append("## 5. How to Visualize")
    lines.append("")
    lines.append("```bash")
    lines.append("# Launch 3D viewer")
    lines.append("python viewer/serve_viewer.py")
    lines.append("# → Open http://localhost:8080")
    lines.append("# → Load: {}".format(
        os.path.join(WORK_DIR, "result_mesh.json")
    ))
    lines.append("```")
    lines.append("")

    lines.append("---")
    lines.append("*Report generated by ABAQUS MCP Pro — Complete Case*")
    lines.append("")

    report_path = os.path.join(WORK_DIR, "simulation_report.md")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    log("  Report saved: {}".format(report_path))

    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log("=" * 60)
    log("COMPLETE CASE: Plate with a Hole — Stress Concentration")
    log("=" * 60)
    log("")

    # 1. Build
    model_info = build_model()

    # 2. Submit
    job_result = run_job()

    # 3. Extract KPI
    kpis = extract_kpis()

    # 4. Export for 3D viewer
    viewer_path = export_for_viewer()

    # 5. Generate report
    report_path = generate_report(model_info, job_result, kpis, viewer_path)

    # -- Final summary --
    log("")
    log("=" * 60)
    log("COMPLETE — All 5 steps finished successfully!")
    log("")
    log("Output directory: {}".format(WORK_DIR))
    log("  KPI:      kpi_summary.json")
    if viewer_path:
        log("  Viewer:   result_mesh.json")
    log("  Report:   simulation_report.md")
    log("")
    log("To view results in 3D:")
    log("  python viewer/serve_viewer.py")
    log("  → Load: {}".format(
        os.path.join(WORK_DIR, "result_mesh.json")
    ))
    log("=" * 60)

    return {
        "model": model_info,
        "job": job_result,
        "kpis": kpis,
        "viewer_json": viewer_path,
        "report": report_path,
    }


if __name__ == "__main__":
    main()
