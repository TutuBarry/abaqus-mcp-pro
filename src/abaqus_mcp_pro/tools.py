"""MCP tool definitions for Abaqus MCP server."""

from __future__ import annotations

import json
import os
from typing import Any

from .transport import _bridge_request, _exec, DEFAULT_HOST, DEFAULT_PORT
from .solver_diagnosis import DIAGNOSE_IN_ABAQUS_CODE
from .odb_lens import KPI_LENS_CODE
from .silent_failures import (SILENT_FAILURE_CHECKS_CODE,
                               format_silent_failures_markdown, parse_silent_failures_results)
from .capsule import CapsuleEntry, CapsuleStore, CAPSULE_CAPTURE_CODE, format_capsule_markdown, format_capsule_list_markdown, diff_capsules
from .contracts import check_contracts, format_contracts_markdown
from .report import format_report_markdown, build_report, save_report
from .abaqus_tools import (
    set_run_python as _set_run_python,
    create_elastic_material,
    create_plastic_material,
    list_materials,
    create_solid_section,
    assign_section,
    create_encastre_bc,
    create_displacement_bc,
    create_pressure_load,
    create_gravity_load,
    create_tie,
    create_static_step,
    create_modal_step,
    create_part_cube,
    create_part_cylinder,
    generate_mesh,
    get_field_output_summary,
    set_viewport_display,
    set_viewport_view,
    set_viewport_annotations,
    create_multiple_viewports,
)
from .abaqus_tools_extended import (
    set_run_python as _set_run_python_ext,
    create_concentrated_force,
    create_moment_load,
    create_shell_edge_load,
    create_line_load,
    create_body_force,
    create_heat_flux_load,
    create_body_heat_flux,
    create_connector_force,
    create_symmetry_bc,
    create_pinned_bc,
    create_velocity_bc,
    create_acceleration_bc,
    create_temperature_bc,
    create_connector_displacement_bc,
    create_rigid_body_constraint,
    create_coupling_constraint,
    create_mpc_constraint,
    create_embedded_region,
    create_equation_constraint,
    create_instance,
    translate_instance,
    rotate_instance,
    create_reference_point,
    create_set_by_face,
    create_set_by_edges,
    create_set_by_vertices,
    create_surface,
    create_surface_by_edges,
    find_face_by_coordinate,
    find_edge_by_coordinate,
    create_contact_property,
    create_surface_to_surface_contact,
    create_surface_to_surface_contact_exp,
    create_general_contact,
    create_general_contact_exp,
    create_explicit_step,
    create_heat_transfer_step,
    create_coupled_temp_disp_step,
    create_dynamic_implicit_step,
    create_static_riks_step,
    create_buckle_step,
    create_field_output_request,
    create_history_output_request,
    seed_part,
    set_element_type,
    set_mesh_control,
    create_tabular_amplitude,
    create_smooth_step_amplitude,
    create_periodic_amplitude,
    get_xy_data,
    get_history_output,
    get_node_coordinates,
    list_elements,
    list_nodes,
    create_hyperelastic_material,
    create_viscoelastic_material,
    create_thermal_expansion,
    create_thermal_conductivity,
    create_specific_heat,
    create_damage_initiation,
    create_part_sphere,
    create_part_beam,
    create_part_plate,
    create_beam_section,
    create_shell_section,
)

from .convergence_advisor import (
    get_advice_for_patterns,
    format_all_advice_markdown, extract_pattern_ids_from_diagnosis,
)

def _json_string(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _unwrap_execution_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok", False):
        raise RuntimeError(_format_error_to_markdown(result))
    return result



def _format_error_to_markdown(result: dict[str, Any]) -> str:
    """Render a crash payload into a compact, highly readable Markdown diagnostic panel."""
    parts: list[str] = []

    error_type = result.get("error_type", "Unknown")
    short_type = error_type.rsplit(".", 1)[-1] if "." in error_type else error_type
    core_error = result.get("core_error", "Unknown error")
    error_line = result.get("error_line")

    # Extract message from core_error to avoid prefix duplication
    prefix = f"{short_type}:"
    if core_error.startswith(prefix):
        msg = core_error[len(prefix):].strip()
    else:
        msg = core_error

    location = f" at line {error_line}" if error_line else ""
    parts.append(f"{short_type}{location}: {msg}")

    # Indented recovery details, organized by error type
    recovery = result.get("recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    if recovery:
        # KeyError details
        if "missing_key" in recovery:
            if recovery.get("parent_object_path"):
                parts.append(f"  Container: {recovery['parent_object_path']}")
            if "available_keys_sample" in recovery:
                sample = recovery["available_keys_sample"]
                if isinstance(sample, list):
                    if len(sample) > 20:
                        sample = sample[:20] + ["..."]
                    parts.append(f"  Available: {sample}")
            if recovery.get("possible_keys"):
                parts.append(f"  Similar: {recovery['possible_keys']}")

        # AttributeError details
        elif "missing_attribute" in recovery:
            parts.append(f"  Missing Attribute: {recovery['missing_attribute']}")
            if recovery.get("object_type"):
                parts.append(f"  Object Type: {recovery['object_type']}")
            if recovery.get("parent_object_path"):
                parts.append(f"  Object Path: {recovery['parent_object_path']}")
            if recovery.get("possible_members"):
                parts.append(f"  Similar: {recovery['possible_members']}")

        # NameError details
        elif "missing_variable" in recovery:
            parts.append(f"  Undefined Variable: {recovery['missing_variable']}")
            if recovery.get("import_suggestion"):
                parts.append(f"  Import Suggestion: {recovery['import_suggestion']}")

        # SyntaxError details
        elif "syntax_line" in recovery:
            if recovery.get("syntax_offset"):
                parts.append(f"  Syntax Error offset: {recovery['syntax_offset']}")
            if recovery.get("syntax_text"):
                parts.append(f"  Problem text: {recovery['syntax_text'].strip()}")

        # TypeError or fallback callable details
        elif "callable_signature" in recovery or "call_target" in recovery:
            if recovery.get("call_target"):
                parts.append(f"  Call Target: {recovery['call_target']}")
            if recovery.get("callable_signature"):
                parts.append(f"  Expected Signature: {recovery['callable_signature']}")
            if recovery.get("callable_summary"):
                parts.append(f"  Description: {recovery['callable_summary']}")
            if recovery.get("possible_keywords"):
                parts.append(f"  Similar Keywords: {recovery['possible_keywords']}")

        # Generic fallback for any other recovery fields
        else:
            if recovery.get("parent_object_path"):
                parts.append(f"  Object: {recovery['parent_object_path']}")
            if recovery.get("import_suggestion"):
                parts.append(f"  Import Suggestion: {recovery['import_suggestion']}")

    # Failed code line - extract only the line marked with >>
    code_excerpt = result.get("code_excerpt")
    if code_excerpt:
        for line in code_excerpt.splitlines():
            if line.startswith(">>"):
                parts_line = line.split("|", 1)
                if len(parts_line) == 2:
                    failed_line = parts_line[1].strip()
                    parts.append(f"  Code: {failed_line}")
                break

    # stdout/stderr summary & content
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    if stdout:
        lines_count = len(stdout.splitlines())
        if lines_count <= 3:
            parts.append(f"  stdout: {stdout}")
        else:
            parts.append(f"  stdout: (captured, {lines_count} lines)")
    if stderr:
        lines_count = len(stderr.splitlines())
        if lines_count <= 3:
            parts.append(f"  stderr: {stderr}")
        else:
            parts.append(f"  stderr: (captured, {lines_count} lines)")

    return "\n".join(parts)

async def ping(timeout: float | None = None) -> dict[str, Any]:
    """Check whether the Abaqus-side socket bridge is reachable."""
    return await _bridge_request("ping", timeout=timeout or 10.0)


async def check_abaqus_connection(timeout: float | None = None) -> str:
    """Return a concise human-readable bridge status."""
    info = await ping(timeout=timeout or 10.0)
    models = info.get("models", [])
    viewports = info.get("viewports", [])
    version = info.get("abaqus_version") or "unknown"
    return (
        f"Connected to Abaqus socket bridge at {DEFAULT_HOST}:{DEFAULT_PORT}.\n"
        f"Abaqus version: {version}\n"
        f"Models: {models}\n"
        f"Viewports: {viewports}"
    )


async def run_python(code: str, timeout: float | None = None) -> dict[str, Any]:
    """Execute Python code in the active Abaqus/CAE kernel.

    Single-line expressions are evaluated and returned. Multi-line scripts are
    executed; set a variable named ``result`` to return structured data.
    """
    if not code.strip():
        raise ValueError("code must not be empty")
    return _unwrap_execution_result(await _exec(code, timeout))


async def execute_script(script: str, timeout: float | None = None) -> str:
    """Compatibility wrapper around run_python that returns stdout/text."""
    result = await run_python(script, timeout)
    stdout = str(result.get("stdout") or "")
    returned = result.get("return_value")
    if returned is not None:
        if stdout:
            return stdout + "\n" + _json_string(returned)
        return _json_string(returned)
    return stdout if stdout else "(Script executed successfully, no output)"


async def set_workdir(path: str, timeout: float | None = None) -> dict[str, Any]:
    """Change the current Abaqus working directory."""
    if not path.strip():
        raise ValueError("path must not be empty")
    code = r"""
import os

new_path = __PATH__
old_dir = os.getcwd()
if not os.path.isdir(new_path):
    raise OSError("Directory does not exist: " + new_path)
os.chdir(new_path)
result = {"success": True, "previous": old_dir, "current": os.getcwd()}
""".replace("__PATH__", json.dumps(path.strip()))
    return (await run_python(code, timeout)).get("return_value")


async def get_model_info(timeout: float | None = None) -> str:
    """Get parts, materials, steps, loads, BCs, interactions, jobs, and viewports."""
    code = r"""
from abaqus import mdb, session

def _keys(obj):
    try:
        return list(obj.keys())
    except Exception:
        return []

models = {}
for model_name in mdb.models.keys():
    model = mdb.models[model_name]
    model_info = {
        "parts": _keys(model.parts),
        "materials": _keys(model.materials),
        "sections": _keys(model.sections),
        "steps": _keys(model.steps),
        "loads": _keys(model.loads),
        "boundary_conditions": _keys(model.boundaryConditions),
        "interactions": _keys(model.interactions),
        "constraints": _keys(model.constraints),
        "amplitudes": _keys(model.amplitudes),
        "assembly_instances": _keys(model.rootAssembly.instances),
        "sets": _keys(model.rootAssembly.sets),
        "surfaces": _keys(model.rootAssembly.surfaces),
    }
    part_details = {}
    for part_name in model.parts.keys():
        part = model.parts[part_name]
        part_details[part_name] = {
            "cells": len(getattr(part, "cells", [])),
            "faces": len(getattr(part, "faces", [])),
            "edges": len(getattr(part, "edges", [])),
            "vertices": len(getattr(part, "vertices", [])),
            "sets": _keys(part.sets),
            "surfaces": _keys(part.surfaces),
        }
    model_info["part_details"] = part_details
    models[model_name] = model_info

jobs = []
for job_name in mdb.jobs.keys():
    job = mdb.jobs[job_name]
    item = {"name": job_name}
    for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    jobs.append(item)

result = {
    "models": models,
    "jobs": jobs,
    "current_viewport": getattr(session, "currentViewportName", None),
    "viewports": list(session.viewports.keys()) if hasattr(session, "viewports") else [],
}
"""
    return _json_string((await run_python(code, timeout)).get("return_value"))


async def list_jobs(timeout: float | None = None) -> str:
    """List all Abaqus jobs in the current CAE session."""
    code = r"""
from abaqus import mdb

jobs = []
for name in mdb.jobs.keys():
    job = mdb.jobs[name]
    item = {"name": name}
    for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory", "explicitPrecision"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    jobs.append(item)
result = {"jobs": jobs}
"""
    return _json_string((await run_python(code, timeout)).get("return_value"))


async def submit_job(job_name: str, timeout: float | None = None) -> str:
    """Submit an existing Abaqus job and wait for completion."""
    if not job_name.strip():
        raise ValueError("job_name must not be empty")
    code = r"""
from abaqus import mdb

job_name = __JOB_NAME__
if job_name not in mdb.jobs:
    raise KeyError("Job not found: " + job_name)
job = mdb.jobs[job_name]
job.submit(consistencyChecking=False)
job.waitForCompletion()
result = {"success": True, "job": job_name, "status": str(getattr(job, "status", "UNKNOWN"))}
""".replace("__JOB_NAME__", json.dumps(job_name.strip()))
    return _json_string((await run_python(code, timeout or 3600.0)).get("return_value"))


async def monitor_job_status(job_name: str = "", diagnose: bool = False, timeout: float | None = None) -> dict[str, Any]:
    """Inspect job objects and tail .sta/.msg diagnostics. Set diagnose=True for full solver-log analysis."""
    code = r"""
import os
import re
from abaqus import mdb

job_name = __JOB_NAME__

def _tail_lines(path, count):
    try:
        with open(path, "r") as handle:
            lines = handle.read().splitlines()
        return lines[-count:]
    except Exception:
        return []

def _grep_tail(path, patterns, limit):
    try:
        rx = re.compile("|".join(patterns))
        matches = []
        with open(path, "r") as handle:
            for line in handle:
                if rx.search(line):
                    matches.append(line.rstrip())
        return matches[-limit:]
    except Exception:
        return []

if not job_name:
    jobs = []
    for name in mdb.jobs.keys():
        job = mdb.jobs[name]
        item = {"name": name}
        for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory"):
            try:
                value = getattr(job, attr, None)
                if value is not None:
                    item[attr] = str(value)
            except Exception:
                pass
        jobs.append(item)
    result = {"jobs": jobs, "workdir": os.getcwd()}
else:
    sta_path = os.path.join(os.getcwd(), job_name + ".sta")
    msg_path = os.path.join(os.getcwd(), job_name + ".msg")
    result = {
        "job_name": job_name,
        "workdir": os.getcwd(),
        "sta_path": sta_path,
        "msg_path": msg_path,
        "progress_tail": _tail_lines(sta_path, 8),
        "diagnostics_tail": _grep_tail(msg_path, [r"^\*\*\*ERROR", r"^\*\*\*WARNING"], 12),
    }
""".replace("__JOB_NAME__", json.dumps(job_name.strip()))
    result = (await run_python(code, timeout)).get("return_value")

    # If diagnose=True, also run the solver diagnosis and merge results
    if diagnose and job_name:
        try:
            diag_result = await diagnose_job(job_name, timeout=timeout)
            if isinstance(result, dict):
                result["diagnosis"] = diag_result
        except Exception:
            pass
    return result

async def diagnose_job(
    job_name: str,
    workdir: str = "",
    timeout: float | None = None,
) -> str:
    """Run a comprehensive solver-log diagnosis on a job's output files.

    Scans .sta, .msg, .dat, .log files for 40+ known error/warning patterns
    across 14 categories: license, convergence, model setup, contact,
    material, resources, environment, ODB, syntax, explicit, output,
    scripting, mesh, and general.

    Returns a structured Markdown diagnostic panel with severity markers,
    source file references, and actionable fix suggestions.
    """
    if not job_name.strip():
        raise ValueError("job_name must not be empty")
    wd = json.dumps(workdir.strip() if workdir.strip() else "")
    code = DIAGNOSE_IN_ABAQUS_CODE.replace("__JOB_NAME__", json.dumps(job_name.strip())).replace("__WORKDIR__", wd)
    code = code.replace(
        '_WORKDIR = ""',
        '_WORKDIR = os.getcwd() if _WORKDIR == "" else _WORKDIR',
    )
    raw_result = await run_python(code, timeout)
    report_data = raw_result.get("return_value")
    if not isinstance(report_data, dict):
        return f"Diagnosis failed: unexpected result type {type(report_data)}"
    return _format_diagnosis_report_markdown(report_data)


def _format_diagnosis_report_markdown(report: dict) -> str:
    """Render a diagnosis report dict as structured Markdown."""
    lines: list[str] = []
    job_name = report.get("job_name", "unknown")
    workdir = report.get("workdir", "")
    files_scanned = report.get("files_scanned", [])
    error_count = report.get("error_count", 0)
    warning_count = report.get("warning_count", 0)
    info_count = report.get("info_count", 0)
    events = report.get("events", [])

    lines.append(f"## Solver Diagnosis: `{job_name}`")
    lines.append("")
    lines.append(f"**Workdir:** `{workdir}`")
    lines.append(f"**Files scanned:** {', '.join(files_scanned) or '(none found)'}")
    lines.append("")

    parts = []
    if error_count:
        parts.append(f"{error_count} error(s)")
    if warning_count:
        parts.append(f"{warning_count} warning(s)")
    if info_count:
        parts.append(f"{info_count} info")
    if not parts:
        parts.append("No issues detected")
    lines.append(f"**Summary:** {' | '.join(parts)}")
    lines.append("")

    if not events:
        lines.append("No diagnostic events found. The solver output appears clean.")
        return "\n".join(lines)

    from collections import defaultdict
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        grouped[e.get("category", "unknown")].append(e)

    category_icons = {
        "license": " License", "convergence": " Convergence", "model_setup": " Setup",
        "contact": " Contact", "material": " Material", "resources": " Resources",
        "environment": " Environment", "odb": " ODB", "syntax": " Syntax",
        "explicit": " Explicit", "output": " Output", "scripting": " Scripting",
        "mesh": " Mesh", "general": " General",
    }

    for category_name, cat_events in sorted(grouped.items()):
        icon = category_icons.get(category_name, "")
        lines.append(f"###{icon} {category_name.replace('_', ' ').title()}")
        lines.append("")

        seen_ids: set[str] = set()
        for e in cat_events:
            pid = e.get("pattern_id", "?")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            severity = e.get("severity", "info")
            marker = "[ERROR]" if severity == "error" else ("[WARN]" if severity == "warning" else "[INFO]")
            lines.append(f"**{marker} {pid}**")
            lines.append(f"> {e.get('suggestion', 'No suggestion available.')}")
            lines.append(f"> *Source: `{e.get('file', '?')}` line {e.get('line', '?')}*")
            lines.append("")
            lines.append("```")
            lines.append(e.get("raw_line", ""))
            lines.append("```")
            lines.append("")

    lines.append("---")
    lines.append("*Diagnosis generated by abaqus-mcp-pro Solver Doctor.*")
    return "\n".join(lines)




async def inspect_odb(odb_path: str, timeout: float | None = None) -> dict[str, Any]:
    """Open an ODB read-only and return metadata about steps, frames, and outputs."""
    if not odb_path.strip():
        raise ValueError("odb_path must not be empty")
    code = r"""
from odbAccess import openOdb

odb_path = __ODB_PATH__
odb = None
try:
    odb = openOdb(path=odb_path, readOnly=True)
    steps = []

    def _slice_frames(frames):
        count = len(frames)
        if count <= 5:
            return [(i, frames[i]) for i in range(count)]
        idxs = [0, int(round((count - 1) * 0.25)), int(round((count - 1) * 0.5)), int(round((count - 1) * 0.75)), count - 1]
        seen = []
        for idx in idxs:
            if idx not in seen:
                seen.append(idx)
        return [(i, frames[i]) for i in seen]

    for step_name in odb.steps.keys():
        step = odb.steps[step_name]
        frame_items = []
        for idx, frame in _slice_frames(step.frames):
            frame_items.append({
                "index": idx,
                "frameId": frame.frameId,
                "frameValue": frame.frameValue,
                "description": str(getattr(frame, "description", "")),
            })

        field_outputs = []
        history_outputs = []
        if step.frames:
            try:
                for key in step.frames[-1].fieldOutputs.keys():
                    field = step.frames[-1].fieldOutputs[key]
                    field_outputs.append({
                        "name": key,
                        "position": str(getattr(field, "position", "")),
                        "components": list(getattr(field, "componentLabels", []) or []),
                        "validInvariants": [str(x) for x in (getattr(field, "validInvariants", []) or [])],
                    })
            except Exception:
                pass
            try:
                history_outputs = list(step.historyRegions.keys())
            except Exception:
                pass

        steps.append({
            "name": step_name,
            "procedure": str(getattr(step, "procedure", "")),
            "totalTime": getattr(step, "totalTime", 0.0),
            "frame_count": len(step.frames),
            "frames": frame_items,
            "fieldOutputs": field_outputs,
            "historyRegions": history_outputs,
        })

    result = {
        "title": str(getattr(odb, "title", "")),
        "description": str(getattr(odb, "description", "")),
        "parts": list(odb.parts.keys()) if hasattr(odb, "parts") else [],
        "instances": list(odb.rootAssembly.instances.keys()) if hasattr(odb, "rootAssembly") else [],
        "steps": steps,
    }
finally:
    if odb is not None:
        odb.close()
""".replace("__ODB_PATH__", json.dumps(odb_path.strip()))
    return (await run_python(code, timeout or 120.0)).get("return_value")


async def get_odb_info(odb_path: str, timeout: float | None = None) -> str:
    """Compatibility wrapper for inspect_odb returning formatted JSON."""
    return _json_string(await inspect_odb(odb_path, timeout))


async def extract_kpis(
    odb_path: str,
    queries: str,
    timeout: float | None = None,
) -> str:
    """Extract KPIs from an ODB file using declarative queries.

    ``queries`` is a JSON array of query objects, each with:
    - query_id (str): unique identifier for this KPI
    - field (str): field output name, e.g. "S", "U", "RF", "PEEQ", "NT"
    - component (str, optional): e.g. "Mises", "U1", "S11", "RF2"
    - invariant (str, optional): e.g. "Mises", "MaxPrincipal", "Tresca"
    - step (str, optional): step name, default first step
    - frame (str, optional): "last", "first", or frame index, default "last"
    - aggregation (str, optional): max, min, sum, avg, range, abs_max, default "max"
    - region (str, optional): node/element set name, default ALL

    Example queries JSON:
    [
      {"query_id": "max_stress", "field": "S", "invariant": "Mises", "aggregation": "max"},
      {"query_id": "max_disp", "field": "U", "component": "Magnitude", "aggregation": "max"},
      {"query_id": "rf_sum", "field": "RF", "component": "RF2", "aggregation": "sum", "region": "FIXED_END"}
    ]

    Returns a structured Markdown KPI report.
    """
    if not odb_path.strip():
        raise ValueError("odb_path must not be empty")
    if not queries.strip():
        raise ValueError("queries must not be empty")

    # Validate queries JSON
    try:
        parsed = json.loads(queries)
        if not isinstance(parsed, list):
            raise ValueError("queries must be a JSON array")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid queries JSON: {e}") from e

    code = (
        KPI_LENS_CODE
        .replace("__ODB_PATH__", json.dumps(odb_path.strip()))
        .replace("__QUERIES_JSON__", json.dumps(queries))
    )
    raw_result = await run_python(code, timeout or 120.0)
    report_data = raw_result.get("return_value")
    if not isinstance(report_data, dict):
        return f"KPI extraction failed: unexpected result type {type(report_data)}"
    return _format_kpi_lens_markdown(report_data)


def _format_kpi_lens_markdown(report: dict) -> str:
    """Render a KPI lens report dict as structured Markdown."""
    lines: list[str] = []
    odb_path = report.get("odb_path", "unknown")
    results = report.get("results", [])
    error_count = report.get("error_count", 0)
    ok_count = len(results) - error_count

    lines.append(f"## ODB Lens: `{os.path.basename(odb_path)}`")
    lines.append("")
    lines.append(f"**ODB:** `{odb_path}`")
    lines.append("")

    if not results:
        lines.append("No queries executed.")
        return "\n".join(lines)

    lines.append(f"**Results:** {ok_count} OK, {error_count} error(s)")
    lines.append("")

    lines.append("| Query ID | Value | Unit | Metadata |")
    lines.append("|----------|-------|------|----------|")

    for r in results:
        qid = r.get("query_id", "?")
        if r.get("error"):
            lines.append(f"| {qid} | ERROR | 鈥?| {r['error']} |")
        else:
            val = r.get("value")
            if isinstance(val, float):
                # Smart formatting: use scientific notation for very small/large values
                if abs(val) < 0.001 or abs(val) > 1e6:
                    val_str = f"{val:.4e}"
                else:
                    val_str = f"{val:.6g}"
            else:
                val_str = str(val) if val is not None else "N/A"
            unit = r.get("unit", "")
            meta = r.get("metadata", {})
            meta_str = ", ".join(f"{k}={v}" for k, v in meta.items()) if meta else ""
            lines.append(f"| {qid} | {val_str} | {unit} | {meta_str} |")

    lines.append("")
    lines.append("---")
    lines.append("*Extracted by abaqus-mcp-pro ODB Lens.*")
    return "\n".join(lines)


_store = CapsuleStore()

async def create_capsule(
    capsule_id: str,
    notes: str = "",
    timeout: float | None = None,
) -> str:
    """Capture current Abaqus session state into an experiment capsule.

    Saves model info, job status, output file inventory, and Abaqus version
    for reproducibility and later comparison.

    Args:
        capsule_id: Unique identifier for this capsule (e.g. "baseline_v1").
        notes: Optional description of this run.
    """
    if not capsule_id.strip():
        raise ValueError("capsule_id must not be empty")
    code = (
        CAPSULE_CAPTURE_CODE
        .replace("__CAPSULE_ID__", json.dumps(capsule_id.strip()))
        .replace("__NOTES__", json.dumps(notes.strip()))
    )
    raw_result = await run_python(code, timeout)
    capsule_data = raw_result.get("return_value")
    if not isinstance(capsule_data, dict):
        return f"Capsule creation failed: unexpected result type {type(capsule_data)}"

    capsule = CapsuleEntry.from_dict(capsule_data)
    path = _store.save(capsule)
    return f"Capsule `{capsule_id}` saved to `{path}`\n\n{format_capsule_markdown(capsule)}"


async def list_capsules() -> str:
    """List all saved experiment capsules."""
    capsules = _store.list_all()
    return format_capsule_list_markdown(capsules)


async def load_capsule(capsule_id: str) -> str:
    """Load a saved experiment capsule by ID."""
    if not capsule_id.strip():
        raise ValueError("capsule_id must not be empty")
    capsule = _store.load(capsule_id.strip())
    if capsule is None:
        return f"Capsule `{capsule_id}` not found. Available: {', '.join(_store.list_ids())}"
    return format_capsule_markdown(capsule)


async def delete_capsule(capsule_id: str) -> str:
    """Delete a saved experiment capsule."""
    if not capsule_id.strip():
        raise ValueError("capsule_id must not be empty")
    if _store.delete(capsule_id.strip()):
        return f"Capsule `{capsule_id}` deleted."
    return f"Capsule `{capsule_id}` not found."


async def compare_capsules(capsule_id_1: str, capsule_id_2: str) -> str:
    """Compare two experiment capsules and show differences."""
    if not capsule_id_1.strip() or not capsule_id_2.strip():
        raise ValueError("Both capsule IDs must be provided")
    c1 = _store.load(capsule_id_1.strip())
    c2 = _store.load(capsule_id_2.strip())
    if c1 is None:
        return f"Capsule `{capsule_id_1}` not found."
    if c2 is None:
        return f"Capsule `{capsule_id_2}` not found."
    return diff_capsules(c1, c2)

async def check_physics_contracts(
    contracts_json: str,
    kpis_json: str = "",
    capsule_id: str = "",
) -> str:
    """Check physics contracts against KPI values from a capsule or direct JSON.

    Validates that simulation results meet design requirements defined as
    contracts (range, threshold, exact, pct_change). Supports two modes:
    1. Direct mode: provide contracts_json and kpis_json directly.
    2. Capsule mode: provide contracts_json and capsule_id to load KPIs
       from a previously saved experiment capsule.

    Args:
        contracts_json: JSON array of contract dicts. Each dict must have
            contract_id, kpi_name, contract_type. Optional: expected, tolerance,
            severity, description.
        kpis_json: JSON object mapping KPI names to values, e.g. {"max_stress": 345.6}.
            Required if capsule_id is empty.
        capsule_id: Load KPIs from this capsule instead of kpis_json.

    Contract types:
        - range: value must be within [min, max]
        - threshold_gt: value must be greater than X
        - threshold_lt: value must be less than X
        - exact: value must equal X (within tolerance)
        - pct_change: change from baseline must be within X%

    Returns:
        Markdown-formatted contract validation report.
    """
    if not contracts_json.strip():
        raise ValueError("contracts_json must not be empty")

    try:
        contracts = json.loads(contracts_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid contracts_json: {exc}") from exc

    if not isinstance(contracts, list):
        raise ValueError("contracts_json must be a JSON array")

    if capsule_id.strip():
        capsule = _store.load(capsule_id.strip())
        if capsule is None:
            return f"Capsule `{capsule_id}` not found. Available: {', '.join(_store.list_ids())}"
        if not capsule.kpis:
            return f"Capsule `{capsule_id}` has no KPIs stored. Capture a capsule with create_capsule first."
        kpis = capsule.kpis
    elif kpis_json.strip():
        try:
            kpis = json.loads(kpis_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid kpis_json: {exc}") from exc
        if not isinstance(kpis, dict):
            raise ValueError("kpis_json must be a JSON object")
    else:
        raise ValueError("Either kpis_json or capsule_id must be provided")

    report = check_contracts(contracts, kpis)
    return format_contracts_markdown(report)

async def generate_report(
    capsule_id: str = "",
    contracts_json: str = "",
    report_title: str = "Abaqus Simulation Report",
    output_path: str = "",
    include_silent_failures: bool = False,
    timeout: float | None = None,
) -> str:
    """Generate a comprehensive simulation report in Markdown format.

    Combines capsule snapshot, KPI lens results, physics contracts validation,
    solver diagnosis, and silent failure detection into a single structured report.
    Supports two modes:

    1. Full mode: provide capsule_id (and optionally contracts_json).
       The report will include model info, job status, KPIs, solver diagnosis,
       and contract validation from the capsule.

    2. Quick mode: provide contracts_json and kpis_json directly
       (uses check_physics_contracts internally).

    Args:
        capsule_id: Load data from this capsule. If provided, the report
            includes model info, job status, KPIs, and diagnosis from the capsule.
        contracts_json: JSON array of contract dicts to validate against capsule KPIs.
            Only used when capsule_id is provided.
        report_title: Title for the report.
        output_path: If provided, save the report to this file path.
            Otherwise, return the report as text.
        include_silent_failures: If True, run silent-failure checks on the
            model and include the results in the report.

    Returns:
        The generated report as Markdown text, or a confirmation message
        if output_path is provided.
    """
    capsule = None
    contracts = None

    # Load capsule if provided
    if capsule_id.strip():
        capsule = _store.load(capsule_id.strip())
        if capsule is None:
            return f"Capsule `{capsule_id}` not found. Available: {', '.join(_store.list_ids())}"

    # Validate contracts if provided
    if contracts_json.strip() and capsule:
        try:
            contract_list = json.loads(contracts_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid contracts_json: {exc}") from exc
        if not isinstance(contract_list, list):
            raise ValueError("contracts_json must be a JSON array")
        if capsule.kpis:
            contracts = check_contracts(contract_list, capsule.kpis)
        else:
            contracts = check_contracts(contract_list, {})

    # Build diagnosis report from capsule
    diagnosis = None
    if capsule and capsule.diagnosis:
        from .solver_diagnosis import DiagnosisReport, DiagnosticEvent
        diag = DiagnosisReport(
            job_name=capsule.job_name or capsule.capsule_id,
            workdir=capsule.workdir or "",
        )
        for event_dict in capsule.diagnosis.get("events", []):
            diag.add_event(DiagnosticEvent(
                category=event_dict.get("category", "general"),
                severity=event_dict.get("severity", "info"),
                pattern_id=event_dict.get("pattern_id", "unknown"),
                file=event_dict.get("file", ""),
                line=event_dict.get("line", 0),
                raw_line=event_dict.get("raw_line", ""),
                suggestion=event_dict.get("suggestion", ""),
            ))
        diagnosis = diag

    # Build KPILensReport from capsule
    kpi_lens = None
    if capsule and capsule.kpis:
        from .odb_lens import KPILensReport, KPIResult
        kpi = KPILensReport(odb_path=capsule.workdir or "")
        for kpi_name, kpi_value in capsule.kpis.items():
            kpi.add_result(KPIResult(query_id=kpi_name, value=kpi_value))
        kpi_lens = kpi

    # Run silent failure checks if requested
    silent_failures = None
    if include_silent_failures:
        try:
            mn = capsule.capsule_id if capsule else ""
            wd = capsule.workdir if capsule else ""
            sf_code = SILENT_FAILURE_CHECKS_CODE.replace("__MODEL_NAME__", json.dumps(mn)).replace("__WORKDIR__", json.dumps(wd))
            sf_raw = await run_python(sf_code, timeout)
            sf_data = sf_raw.get("return_value")
            if isinstance(sf_data, dict):
                silent_failures = parse_silent_failures_results(sf_data)
        except Exception:
            pass  # Silent failure check is optional, don't block report

    report = build_report(
        title=report_title,
        capsule=capsule,
        kpi_lens=kpi_lens,
        contracts=contracts,
        diagnosis=diagnosis,
        silent_failures=silent_failures,
    )

    md = format_report_markdown(report)

    if output_path.strip():
        saved = save_report(report, output_path.strip())
        return f"Report saved to `{saved}`\n\n{md}"

    return md




async def capture_viewport(
    viewport_name: str = "",
    image_format: str = "PNG",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Capture an Abaqus viewport as base64 image data."""
    code = r"""
import os
import tempfile
import base64
from abaqus import session
import abaqusConstants

vp_name = __VP_NAME__
fmt_name = __FORMAT__.upper()
fmt_map = {
    "PNG": abaqusConstants.PNG,
    "TIFF": abaqusConstants.TIFF,
    "SVG": abaqusConstants.SVG,
    "EPS": abaqusConstants.EPS,
    "PS": abaqusConstants.PS,
}
fmt = fmt_map.get(fmt_name, abaqusConstants.PNG)

if not vp_name or vp_name not in session.viewports.keys():
    vp_name = session.currentViewportName
vp = session.viewports[vp_name]
suffix = "." + fmt_name.lower()
handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
tmp_path = handle.name
handle.close()

try:
    session.printToFile(fileName=tmp_path, format=fmt, canvasObjects=(vp,))
    with open(tmp_path, "rb") as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode("ascii")
    result = {
        "success": True,
        "viewport": vp_name,
        "format": fmt_name.lower(),
        "image_base64": image_base64,
        "size_bytes": int(len(image_base64) * 3 / 4),
    }
finally:
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
""".replace("__VP_NAME__", json.dumps(viewport_name.strip())).replace("__FORMAT__", json.dumps(image_format.strip() or "PNG"))
    return (await run_python(code, timeout or 60.0)).get("return_value")


async def get_viewport_image(viewport_name: str = "", image_format: str = "PNG", timeout: float | None = None) -> str:
    """Compatibility wrapper returning a data URI for the requested viewport."""
    data = await capture_viewport(viewport_name, image_format, timeout)
    fmt = data.get("format", "png")
    b64 = data.get("image_base64", "")
    return f"data:image/{fmt};base64,{b64}"

async def check_silent_failures(
    model_name: str = "",
    workdir: str = "",
    timeout: float | None = None,
) -> str:
    """Run silent-failure checks on the current Abaqus model.

    Detects 7 categories of model issues that Abaqus does not report as errors:
    1. **Mesh integrity**: parts with zero elements, unmeshable hex requests
    2. **Constraint coverage**: tie constraints that may silently drop nodes
    3. **Volume/logic**: cut operations that removed nothing, degenerate geometry
    4. **Contact validity**: contact pairs without adjacency
    5. **Element quality**: risky elements (C3D8R hourglass), hourglass-prone configs
    6. **Job output**: completed jobs with no ODB, meaningless exit codes
    7. **Unconstrained parts**: instances free to undergo rigid body motion

    These checks measure the model you built, not just the answer it produced.

    Args:
        model_name: Name of the model to check (default: first available model).
        workdir: Working directory for job output checks (default: current).

    Returns:
        Structured Markdown report with pass/fail/warning findings.
    """
    mn = json.dumps(model_name.strip() if model_name.strip() else "")
    wd = json.dumps(workdir.strip() if workdir.strip() else "")
    code = SILENT_FAILURE_CHECKS_CODE.replace("__MODEL_NAME__", mn).replace("__WORKDIR__", wd)
    raw_result = await run_python(code, timeout)
    report_data = raw_result.get("return_value")
    if not isinstance(report_data, dict):
        return f"Silent failure check failed: unexpected result type {type(report_data)}"
    report = parse_silent_failures_results(report_data)
    return format_silent_failures_markdown(report)


async def check_model_integrity(
    model_name: str = "",
    timeout: float | None = None,
) -> str:
    """Quick model integrity check: mesh, constraints, contacts, volumes.

    A fast subset of check_silent_failures focused on the most common
    silent failures. Runs the same checks but returns a compact format.

    Use this after building a model and before submitting a job.

    Args:
        model_name: Name of the model to check (default: first available model).

    Returns:
        Compact text report of findings.
    """
    mn = json.dumps(model_name.strip() if model_name.strip() else "")
    code = SILENT_FAILURE_CHECKS_CODE.replace("__MODEL_NAME__", mn).replace("__WORKDIR__", json.dumps(""))
    raw_result = await run_python(code, timeout)
    report_data = raw_result.get("return_value")
    if not isinstance(report_data, dict):
        return f"Integrity check failed: unexpected result type {type(report_data)}"
    report = parse_silent_failures_results(report_data)
    from .silent_failures import format_silent_failures_compact
    return format_silent_failures_compact(report)


async def converge_advice(
    diagnosis_result: str = "",
    pattern_ids: str = "",
    timeout: float | None = None,
) -> str:
    """Get auto-fix suggestions for convergence problems diagnosed by the Solver Doctor.

    Supports two modes:
    1. From diagnosis: pass the result of diagnose_job as diagnosis_result (JSON string).
       The advisor extracts error/warning patterns and returns ranked fix suggestions.
    2. Direct: pass comma-separated pattern_ids to get advice for specific patterns.

    Each suggestion includes:
    - Priority (1 = try first, 5 = last resort)
    - Risk level (low/medium/high)
    - Code template for the fix (where applicable)
    - Description of what to do

    Patterns supported: too_many_attempts, time_increment_too_small,
    maximum_increments_exceeded, negative_eigenvalues, rigid_body_motion,
    contact_overclosure, excessive_distortion, explicit_stable_time_too_small,
    zero_pivot, material_instability, excessive_pivot_ratio.

    Args:
        diagnosis_result: JSON string from diagnose_job output.
            If provided, pattern_ids is ignored.
        pattern_ids: Comma-separated pattern IDs (e.g., "too_many_attempts,rigid_body_motion").
            Only used if diagnosis_result is empty.

    Returns:
        Markdown-formatted fix suggestions with priority and risk levels.
    """
    import json

    if diagnosis_result.strip():
        # Try to parse as JSON diagnosis report
        try:
            diag = json.loads(diagnosis_result.strip())
        except json.JSONDecodeError:
            return "Error: diagnosis_result must be valid JSON from diagnose_job."

        # Handle both raw dict and markdown-wrapped results
        if isinstance(diag, str):
            # Try to find JSON in the markdown
            import re
            match = re.search(r"\{.*\}", diag, re.DOTALL)
            if match:
                try:
                    diag = json.loads(match.group())
                except json.JSONDecodeError:
                    return "Error: Could not extract JSON from diagnosis_result."
            else:
                return "Error: Could not find JSON in diagnosis_result."

        pattern_ids_list = extract_pattern_ids_from_diagnosis(diag)
        if not pattern_ids_list:
            return "No convergence issues found in the diagnosis. The solver output appears clean."

        advice_list = get_advice_for_patterns(pattern_ids_list)
        if not advice_list:
            return f"Diagnosed patterns ({', '.join(pattern_ids_list)}) have no known auto-fixes."

        return format_all_advice_markdown(advice_list)

    elif pattern_ids.strip():
        pids = [p.strip() for p in pattern_ids.split(",") if p.strip()]
        if not pids:
            return "Error: pattern_ids must be a comma-separated list."

        advice_list = get_advice_for_patterns(pids)
        if not advice_list:
            return f"None of the specified patterns ({', '.join(pids)}) have known auto-fixes."

    else:
        return (
            "Please provide either diagnosis_result (from diagnose_job) or pattern_ids (comma-separated list). "
            "Known patterns: too_many_attempts, time_increment_too_small, "
            "maximum_increments_exceeded, negative_eigenvalues, rigid_body_motion, "
            "contact_overclosure, excessive_distortion, explicit_stable_time_too_small, "
            "zero_pivot, material_instability, excessive_pivot_ratio."
        )


def register_tools(mcp) -> None:
    # Inject run_python into aba_utils
    _set_run_python(run_python)
    _set_run_python_ext(run_python)

    """Register all MCP tools with the given MCPServer instance."""
    mcp_tool = mcp.tool()

    mcp_tool(ping)
    mcp_tool(check_abaqus_connection)
    mcp_tool(run_python)
    mcp_tool(execute_script)
    mcp_tool(set_workdir)
    mcp_tool(get_model_info)
    mcp_tool(list_jobs)
    mcp_tool(submit_job)
    mcp_tool(monitor_job_status)
    mcp_tool(diagnose_job)
    mcp_tool(inspect_odb)
    mcp_tool(get_odb_info)
    mcp_tool(extract_kpis)
    mcp_tool(create_capsule)
    mcp_tool(list_capsules)
    mcp_tool(load_capsule)
    mcp_tool(delete_capsule)
    mcp_tool(compare_capsules)
    mcp_tool(check_physics_contracts)
    mcp_tool(generate_report)
    mcp_tool(capture_viewport)
    mcp_tool(get_viewport_image)
    mcp_tool(check_silent_failures)
    mcp_tool(check_model_integrity)
    mcp_tool(converge_advice)

    # Abaqus API tools
    mcp_tool(create_elastic_material)
    mcp_tool(create_plastic_material)
    mcp_tool(list_materials)
    mcp_tool(create_solid_section)
    mcp_tool(assign_section)
    mcp_tool(create_encastre_bc)
    mcp_tool(create_displacement_bc)
    mcp_tool(create_pressure_load)
    mcp_tool(create_gravity_load)
    mcp_tool(create_tie)
    mcp_tool(create_static_step)
    mcp_tool(create_modal_step)
    mcp_tool(create_part_cube)
    mcp_tool(create_part_cylinder)
    mcp_tool(generate_mesh)
    mcp_tool(get_field_output_summary)
    mcp_tool(set_viewport_display)
    mcp_tool(set_viewport_view)
    mcp_tool(set_viewport_annotations)
    mcp_tool(create_multiple_viewports)

    # Extended Abaqus API tools - Loads
    mcp_tool(create_concentrated_force)
    mcp_tool(create_moment_load)
    mcp_tool(create_shell_edge_load)
    mcp_tool(create_line_load)
    mcp_tool(create_body_force)
    mcp_tool(create_heat_flux_load)
    mcp_tool(create_body_heat_flux)
    mcp_tool(create_connector_force)

    # Extended Abaqus API tools - BCs
    mcp_tool(create_symmetry_bc)
    mcp_tool(create_pinned_bc)
    mcp_tool(create_velocity_bc)
    mcp_tool(create_acceleration_bc)
    mcp_tool(create_temperature_bc)
    mcp_tool(create_connector_displacement_bc)

    # Extended Abaqus API tools - Constraints
    mcp_tool(create_rigid_body_constraint)
    mcp_tool(create_coupling_constraint)
    mcp_tool(create_mpc_constraint)
    mcp_tool(create_embedded_region)
    mcp_tool(create_equation_constraint)

    # Extended Abaqus API tools - Assembly
    mcp_tool(create_instance)
    mcp_tool(translate_instance)
    mcp_tool(rotate_instance)
    mcp_tool(create_reference_point)

    # Extended Abaqus API tools - Sets & Surfaces
    mcp_tool(create_set_by_face)
    mcp_tool(create_set_by_edges)
    mcp_tool(create_set_by_vertices)
    mcp_tool(create_surface)
    mcp_tool(create_surface_by_edges)
    mcp_tool(find_face_by_coordinate)
    mcp_tool(find_edge_by_coordinate)

    # Extended Abaqus API tools - Contact/Interaction
    mcp_tool(create_contact_property)
    mcp_tool(create_surface_to_surface_contact)
    mcp_tool(create_surface_to_surface_contact_exp)
    mcp_tool(create_general_contact)
    mcp_tool(create_general_contact_exp)

    # Extended Abaqus API tools - More Steps
    mcp_tool(create_explicit_step)
    mcp_tool(create_heat_transfer_step)
    mcp_tool(create_coupled_temp_disp_step)
    mcp_tool(create_dynamic_implicit_step)
    mcp_tool(create_static_riks_step)
    mcp_tool(create_buckle_step)

    # Extended Abaqus API tools - Output Requests
    mcp_tool(create_field_output_request)
    mcp_tool(create_history_output_request)

    # Extended Abaqus API tools - Mesh Controls
    mcp_tool(seed_part)
    mcp_tool(set_element_type)
    mcp_tool(set_mesh_control)

    # Extended Abaqus API tools - Amplitude
    mcp_tool(create_tabular_amplitude)
    mcp_tool(create_smooth_step_amplitude)
    mcp_tool(create_periodic_amplitude)

    # Extended Abaqus API tools - More Post-Processing
    mcp_tool(get_xy_data)
    mcp_tool(get_history_output)
    mcp_tool(get_node_coordinates)
    mcp_tool(list_elements)
    mcp_tool(list_nodes)

    # Extended Abaqus API tools - More Materials
    mcp_tool(create_hyperelastic_material)
    mcp_tool(create_viscoelastic_material)
    mcp_tool(create_thermal_expansion)
    mcp_tool(create_thermal_conductivity)
    mcp_tool(create_specific_heat)
    mcp_tool(create_damage_initiation)

    # Extended Abaqus API tools - More Geometry
    mcp_tool(create_part_sphere)
    mcp_tool(create_part_beam)
    mcp_tool(create_part_plate)

    # Extended Abaqus API tools - More Sections
    mcp_tool(create_beam_section)
    mcp_tool(create_shell_section)
