"""Solver log diagnosis: scan Abaqus output files (.sta, .msg, .dat, .log)
for known error patterns and produce structured diagnostic reports.

This module is self-contained (stdlib only) so it can both run standalone
and be executed inside the Abaqus kernel via ``run_python``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DiagnosticEvent:
    """A single diagnostic match found in a log file."""

    category: str
    severity: str  # "error", "warning", "info"
    pattern_id: str
    file: str  # filename (e.g. "job.sta")
    line: int
    raw_line: str
    suggestion: str


@dataclass
class DiagnosisReport:
    """Aggregated diagnosis for a single job."""

    job_name: str
    workdir: str = ""
    files_scanned: list[str] = field(default_factory=list)
    events: list[DiagnosticEvent] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    def add_event(self, event: DiagnosticEvent) -> None:
        self.events.append(event)
        if event.severity == "error":
            self.error_count += 1
        elif event.severity == "warning":
            self.warning_count += 1
        else:
            self.info_count += 1

    def to_dict(self) -> dict:
        return {
            "job_name": self.job_name,
            "workdir": self.workdir,
            "files_scanned": self.files_scanned,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "events": [
                {
                    "category": e.category,
                    "severity": e.severity,
                    "pattern_id": e.pattern_id,
                    "file": e.file,
                    "line": e.line,
                    "raw_line": e.raw_line,
                    "suggestion": e.suggestion,
                }
                for e in self.events
            ],
        }


# ---------------------------------------------------------------------------
# Diagnostic patterns
# ---------------------------------------------------------------------------

# Each pattern is a dict with:
#   id          - unique identifier
#   category    - grouping label
#   severity    - "error" | "warning" | "info"
#   regex       - one or more regex patterns (str or list[str])
#   suggestion  - human-readable fix suggestion
#   file_hint   - which file(s) to scan (None = all)

_PATTERNS: list[dict] = [
    # ── License ──────────────────────────────────────────────────────────
    {
        "id": "license_unavailable",
        "category": "license",
        "severity": "error",
        "regex": [
            r"License\s+.*not\s+available",
            r"All\s+licenses\s+are\s+currently\s+in\s+use",
            r"feature\s+has\s+expired",
            r"License\s+server\s+.*down",
            r"cannot\s+connect\s+to\s+license\s+server",
            r"FLEXnet\s+Licensing\s+error",
        ],
        "suggestion": (
            "License token is unavailable. Wait for other users to finish, "
            "check license server status with `lmstat -a`, or contact your admin."
        ),
        "file_hint": [".log", ".msg", ".dat"],
    },
    {
        "id": "too_many_license_attempts",
        "category": "license",
        "severity": "error",
        "regex": r"Too\s+many\s+attempts\s+to\s+check\s+out",
        "suggestion": (
            "Abaqus retried license checkout too many times. Restart the job, "
            "or check if another process is holding the license."
        ),
        "file_hint": [".log", ".msg"],
    },
    # ── Convergence ──────────────────────────────────────────────────────
    {
        "id": "too_many_attempts",
        "category": "convergence",
        "severity": "error",
        "regex": r"Too\s+many\s+attempts\s+made\s+for\s+this\s+increment",
        "suggestion": (
            "The solver could not converge after repeated cutbacks. "
            "Reduce the initial increment size, add stabilization (0.0002), "
            "refine the mesh in contact regions, or check for rigid body motion."
        ),
        "file_hint": [".msg", ".sta"],
    },
    {
        "id": "time_increment_required_too_small",
        "category": "convergence",
        "severity": "error",
        "regex": [
            r"Time\s+increment\s+required\s+is\s+less\s+than",
            r"time\s+increment\s+.*below\s+minimum",
        ],
        "suggestion": (
            "The required time increment fell below the minimum. "
            "Reduce the minimum increment size, add contact stabilization, "
            "or check for sudden stiffness changes (material instability, buckling)."
        ),
        "file_hint": [".msg", ".sta"],
    },
    {
        "id": "maximum_increments_exceeded",
        "category": "convergence",
        "severity": "error",
        "regex": r"Maximum\s+number\s+of\s+increments\s+exceeded",
        "suggestion": (
            "The step did not complete within the maximum allowed increments. "
            "Increase max increments, reduce load, or use automatic stabilization."
        ),
        "file_hint": [".msg", ".sta"],
    },
    {
        "id": "too_many_cutbacks",
        "category": "convergence",
        "severity": "warning",
        "regex": r"cut-\s*back|cutback",
        "suggestion": (
            "The solver is repeatedly cutting back the time increment. "
            "This often indicates severe nonlinearity. Check contact, material "
            "plasticity, or add automatic stabilization."
        ),
        "file_hint": [".msg", ".sta"],
    },
    {
        "id": "severe_discontinuity_iterations",
        "category": "convergence",
        "severity": "warning",
        "regex": r"severe\s+discontinuity\s+iterations",
        "suggestion": (
            "Severe discontinuity iterations indicate contact status changes. "
            "Check contact pair definitions, adjust penalty stiffness, or use "
            "contact stabilization."
        ),
        "file_hint": [".msg", ".sta"],
    },
    # ── Model Setup / Rigid Body ─────────────────────────────────────────
    {
        "id": "rigid_body_motion",
        "category": "model_setup",
        "severity": "warning",
        "regex": [
            r"rigid\s+body\s+mode",
            r"unconstrained\s+body",
            r"zero\s+pivot.*node",
            r"numerical\s+singularity.*node",
        ],
        "suggestion": (
            "A part or region is unconstrained and can move freely. "
            "Add boundary conditions, tie constraints, or springs to remove "
            "rigid body modes. Check for disconnected regions."
        ),
        "file_hint": [".msg", ".dat"],
    },
    {
        "id": "negative_eigenvalues",
        "category": "model_setup",
        "severity": "warning",
        "regex": [
            r"negative\s+eigenvalue",
            r"system\s+matrix\s+has\s+\d+\s+negative\s+eigenvalues",
        ],
        "suggestion": (
            "Negative eigenvalues suggest material instability or buckling. "
            "Check for hourglassing, use enhanced hourglass control, refine mesh, "
            "or add stabilization."
        ),
        "file_hint": [".msg", ".dat"],
    },
    {
        "id": "numerical_singularity",
        "category": "model_setup",
        "severity": "warning",
        "regex": r"numerical\s+singularity",
        "suggestion": (
            "Numerical singularity detected at a node. This usually means "
            "the node is unconstrained or has a zero-stiffness element. "
            "Check BCs, element quality, and material properties."
        ),
        "file_hint": [".msg", ".dat"],
    },
    {
        "id": "zero_pivot",
        "category": "model_setup",
        "severity": "warning",
        "regex": r"zero\s+pivot",
        "suggestion": (
            "Zero pivot found in the stiffness matrix. This indicates a "
            "local degree of freedom has no stiffness. Check for missing BCs, "
            "disconnected elements, or incorrect material properties."
        ),
        "file_hint": [".msg", ".dat"],
    },
    # ── Contact ──────────────────────────────────────────────────────────
    {
        "id": "contact_overclosure",
        "category": "contact",
        "severity": "warning",
        "regex": r"over\s*closure|overclosure",
        "suggestion": (
            "Contact surfaces are penetrating each other initially. "
            "Use 'Adjust only to remove overclosure' in the contact pair, "
            "or adjust the mesh so surfaces do not overlap."
        ),
        "file_hint": [".msg", ".dat"],
    },
    {
        "id": "contact_chattering",
        "category": "contact",
        "severity": "warning",
        "regex": r"chattering",
        "suggestion": (
            "Contact status is changing rapidly between open/closed. "
            "Increase contact stiffness, use softened contact, or refine "
            "the mesh in the contact zone."
        ),
        "file_hint": [".msg"],
    },
    {
        "id": "contact_pair",
        "category": "contact",
        "severity": "error",
        "regex": r"contact\s+pair.*not\s+found|surface.*not\s+found",
        "suggestion": (
            "A contact pair or surface referenced in the model could not be found. "
            "Check that both surfaces exist and are correctly named."
        ),
        "file_hint": [".msg", ".dat", ".log"],
    },
    # ── Material ─────────────────────────────────────────────────────────
    {
        "id": "material_missing_density",
        "category": "material",
        "severity": "error",
        "regex": [
            r"density.*must\s+be\s+defined",
            r"no\s+density.*defined",
            r"missing\s+mass\s+density",
        ],
        "suggestion": (
            "Density is required for dynamic/modal/gravity analyses. "
            "Add a density to the material definition."
        ),
        "file_hint": [".msg", ".dat", ".log"],
    },
    {
        "id": "material_not_defined",
        "category": "material",
        "severity": "error",
        "regex": [
            r"material.*not\s+defined",
            r"material.*not\s+found",
            r"no\s+material.*assigned",
        ],
        "suggestion": (
            "A material referenced in the model is not defined. "
            "Create the material and assign it to the appropriate section."
        ),
        "file_hint": [".msg", ".dat", ".log"],
    },
    {
        "id": "material_plastic_strain_excessive",
        "category": "material",
        "severity": "warning",
        "regex": r"plastic\s+strain.*exceed|excessive\s+plastic\s+strain",
        "suggestion": (
            "The plastic strain in the material is very large. "
            "Check that the yield stress and hardening data are correct, "
            "and that the applied load is not unrealistically high."
        ),
        "file_hint": [".msg"],
    },
    {
        "id": "material_hyperelastic_unstable",
        "category": "material",
        "severity": "warning",
        "regex": r"hyperelastic.*unstable|Drucker.*stability",
        "suggestion": (
            "The hyperelastic material model may be unstable at the current "
            "strain levels. Check the material constants and the strain range."
        ),
        "file_hint": [".msg", ".dat"],
    },
    # ── Resources ────────────────────────────────────────────────────────
    {
        "id": "memory_allocation",
        "category": "resources",
        "severity": "error",
        "regex": [
            r"memory.*exceeded",
            r"insufficient\s+memory",
            r"out\s+of\s+memory",
            r"cannot\s+allocate",
        ],
        "suggestion": (
            "The job ran out of memory. Reduce mesh density, use fewer CPUs, "
            "or increase the memory allocation in the job settings."
        ),
        "file_hint": [".log", ".msg", ".dat"],
    },
    {
        "id": "disk_full",
        "category": "resources",
        "severity": "error",
        "regex": [
            r"disk\s+full",
            r"no\s+space\s+left",
            r"insufficient\s+disk",
        ],
        "suggestion": (
            "The disk is full. Free up space on the working drive, "
            "or redirect output to a different location."
        ),
        "file_hint": [".log", ".msg"],
    },
    {
        "id": "cpu_count_warning",
        "category": "resources",
        "severity": "info",
        "regex": r"number\s+of\s+cpus|cpu\s+count|parallelization",
        "suggestion": "Check that the CPU count is appropriate for the model size.",
        "file_hint": [".log", ".msg"],
    },
    # ── Environment ──────────────────────────────────────────────────────
    {
        "id": "path_too_long",
        "category": "environment",
        "severity": "error",
        "regex": r"path.*too\s+long|file\s+name.*too\s+long",
        "suggestion": (
            "A file path exceeds the OS limit. Move the job to a shorter "
            "directory path (e.g., C:\\Temp\\ or /tmp/)."
        ),
        "file_hint": [".log", ".msg"],
    },
    {
        "id": "file_not_found",
        "category": "environment",
        "severity": "error",
        "regex": [
            r"cannot\s+open\s+file",
            r"file\s+not\s+found",
            r"no\s+such\s+file",
            r"does\s+not\s+exist",
        ],
        "suggestion": (
            "A required file is missing. Check that the file path is correct, "
            "the file exists, and the working directory is set properly."
        ),
        "file_hint": [".log", ".msg", ".dat"],
    },
    {
        "id": "scratch_directory_unavailable",
        "category": "environment",
        "severity": "error",
        "regex": r"scratch.*directory|scratch.*not\s+accessible",
        "suggestion": (
            "The scratch directory is not accessible. Set the scratch "
            "environment variable to a valid writable directory."
        ),
        "file_hint": [".log", ".msg"],
    },
    {
        "id": "lock_file_exists",
        "category": "environment",
        "severity": "error",
        "regex": r"lock\s+file.*exists|already\s+in\s+use",
        "suggestion": (
            "A lock file from a previous run still exists. Remove the .lck "
            "file manually, or use `abaqus job=<name> ask_delete=OFF` to avoid it."
        ),
        "file_hint": [".log", ".msg"],
    },
    # ── ODB ──────────────────────────────────────────────────────────────
    {
        "id": "odb_upgrade_required",
        "category": "odb",
        "severity": "error",
        "regex": r"odb.*upgrade|odb.*version",
        "suggestion": (
            "The ODB was created by a newer Abaqus version. "
            "Use `abaqus upgrade` to convert the ODB, or open it with the "
            "same Abaqus version that created it."
        ),
        "file_hint": [".log"],
    },
    {
        "id": "odb_corrupt",
        "category": "odb",
        "severity": "error",
        "regex": r"odb.*corrupt|odb.*damaged|odb.*cannot\s+be\s+opened",
        "suggestion": (
            "The ODB file appears to be corrupted. If the job is still running, "
            "wait for it to finish. Otherwise, try running `abaqus upgrade` "
            "or re-run the analysis."
        ),
        "file_hint": [".log", ".msg"],
    },
    {
        "id": "odb_no_frames",
        "category": "odb",
        "severity": "warning",
        "regex": r"no\s+frames|odb.*empty",
        "suggestion": (
            "The ODB contains no frames. The analysis may have failed before "
            "writing any results. Check .msg and .sta for errors."
        ),
        "file_hint": [".log"],
    },
    # ── Syntax / Keyword ─────────────────────────────────────────────────
    {
        "id": "keyword_error",
        "category": "syntax",
        "severity": "error",
        "regex": r"\*\*\*ERROR.*keyword|keyword.*error|unknown\s+keyword",
        "suggestion": (
            "An input file keyword is not recognized. Check for typos in "
            "the keyword name, verify the keyword is supported in this "
            "Abaqus version, and check the keyword parameter syntax."
        ),
        "file_hint": [".dat", ".msg", ".log"],
    },
    {
        "id": "element_type_unknown",
        "category": "syntax",
        "severity": "error",
        "regex": r"element\s+type.*not\s+recognized|unknown\s+element\s+type",
        "suggestion": (
            "The element type is not valid. Check the Abaqus documentation "
            "for valid element type codes and ensure the element is appropriate "
            "for the analysis type."
        ),
        "file_hint": [".dat", ".msg"],
    },
    {
        "id": "missing_node_set",
        "category": "syntax",
        "severity": "error",
        "regex": r"node\s+set.*not\s+found|nodeset.*not\s+found",
        "suggestion": (
            "A node set referenced in the model does not exist. "
            "Create the node set or correct the name."
        ),
        "file_hint": [".dat", ".msg"],
    },
    {
        "id": "missing_element_set",
        "category": "syntax",
        "severity": "error",
        "regex": r"element\s+set.*not\s+found|elset.*not\s+found",
        "suggestion": (
            "An element set referenced in the model does not exist. "
            "Create the element set or correct the name."
        ),
        "file_hint": [".dat", ".msg"],
    },
    {
        "id": "missing_surface",
        "category": "syntax",
        "severity": "error",
        "regex": r"surface.*not\s+found",
        "suggestion": (
            "A surface referenced in the model does not exist. "
            "Create the surface or correct the name."
        ),
        "file_hint": [".dat", ".msg"],
    },
    {
        "id": "include_file_missing",
        "category": "syntax",
        "severity": "error",
        "regex": r"INCLUDE.*not\s+found|cannot\s+open\s+include",
        "suggestion": (
            "An included file could not be found. Check that the file path "
            "is correct and the file exists in the working directory."
        ),
        "file_hint": [".dat", ".msg", ".log"],
    },
    # ── Explicit ─────────────────────────────────────────────────────────
    {
        "id": "explicit_stable_time_too_small",
        "category": "explicit",
        "severity": "error",
        "regex": [
            r"stable\s+time\s+increment.*too\s+small",
            r"time\s+increment.*below.*minimum",
        ],
        "suggestion": (
            "The stable time increment in explicit is too small. "
            "Consider mass scaling to increase the time step, or check "
            "for very small/distorted elements."
        ),
        "file_hint": [".sta", ".msg"],
    },
    {
        "id": "excessive_distortion",
        "category": "explicit",
        "severity": "error",
        "regex": r"excessive\s+distortion|element.*distorted",
        "suggestion": (
            "Elements are excessively distorted. Use ALE adaptive meshing, "
            "refine the mesh, or reduce the load/velocity to avoid extreme "
            "deformation."
        ),
        "file_hint": [".msg", ".sta"],
    },
    {
        "id": "explicit_kinetic_energy_ratio",
        "category": "explicit",
        "severity": "warning",
        "regex": r"kinetic\s+energy.*ratio",
        "suggestion": (
            "The ratio of kinetic to internal energy is high. This may "
            "indicate that the loading rate is too fast for a quasi-static "
            "analysis. Slow the loading rate."
        ),
        "file_hint": [".sta"],
    },
    # ── Output ───────────────────────────────────────────────────────────
    {
        "id": "output_variable_invalid",
        "category": "output",
        "severity": "error",
        "regex": r"output\s+variable.*not\s+valid|invalid\s+output",
        "suggestion": (
            "An output variable requested is not valid for this analysis type. "
            "Check the Abaqus output variable list for the current procedure."
        ),
        "file_hint": [".dat", ".msg", ".log"],
    },
    # ── Scripting ────────────────────────────────────────────────────────
    {
        "id": "python_script_error",
        "category": "scripting",
        "severity": "error",
        "regex": [
            r"Python\s+error",
            r"Traceback.*most recent call last",
            r"SyntaxError",
            r"KeyError",
            r"AttributeError",
        ],
        "suggestion": (
            "A Python error occurred during analysis. Check the .log file "
            "for the full traceback, fix the script, and re-run."
        ),
        "file_hint": [".log"],
    },
    {
        "id": "abaqus_command_missing",
        "category": "scripting",
        "severity": "error",
        "regex": r"abaqus.*command\s+not\s+found|abaqus.*not\s+recognized",
        "suggestion": (
            "The abaqus command is not in PATH. Add the Abaqus installation "
            "directory to your PATH environment variable."
        ),
        "file_hint": [".log"],
    },
    # ── Mesh ─────────────────────────────────────────────────────────────
    {
        "id": "mesh_quality_warning",
        "category": "mesh",
        "severity": "warning",
        "regex": r"mesh.*quality|aspect\s+ratio.*exceed|jacobian.*zero",
        "suggestion": (
            "Mesh quality issues detected. Check for elements with high "
            "aspect ratio, small angles, or negative Jacobian. "
            "Use the mesh verification tool or re-mesh the problem region."
        ),
        "file_hint": [".dat", ".msg", ".log"],
    },
    {
        "id": "mesh_too_coarse",
        "category": "mesh",
        "severity": "warning",
        "regex": r"mesh.*too\s+coarse|refine\s+mesh",
        "suggestion": (
            "The mesh may be too coarse for accurate results. "
            "Consider refining the mesh in high-gradient regions."
        ),
        "file_hint": [".msg"],
    },
    # ── General ──────────────────────────────────────────────────────────
    {
        "id": "analysis_completed",
        "category": "general",
        "severity": "info",
        "regex": r"THE\s+ANALYSIS\s+HAS\s+COMPLETED\s+SUCCESSFULLY|COMPLETED|JOB\s+COMPLETED",
        "suggestion": "The analysis completed successfully.",
        "file_hint": [".log", ".msg", ".sta"],
    },
    {
        "id": "analysis_aborted",
        "category": "general",
        "severity": "error",
        "regex": r"THE\s+ANALYSIS\s+HAS\s+BEEN\s+TERMINATED|ABORTED|JOB\s+ABORTED",
        "suggestion": "The analysis was aborted. Check the error messages above.",
        "file_hint": [".log", ".msg", ".sta"],
    },
    {
        "id": "analysis_interrupted",
        "category": "general",
        "severity": "error",
        "regex": r"ANALYSIS\s+INTERRUPTED|JOB\s+INTERRUPTED",
        "suggestion": (
            "The analysis was interrupted. Check if the system was shut down "
            "or if the job was manually killed."
        ),
        "file_hint": [".log", ".msg"],
    },
    {
        "id": "pre_memory_estimate",
        "category": "general",
        "severity": "info",
        "regex": r"memory\s+estimate|estimated\s+memory",
        "suggestion": "Memory estimate for the analysis.",
        "file_hint": [".dat"],
    },
    {
        "id": "restart_data_written",
        "category": "general",
        "severity": "info",
        "regex": r"restart\s+data.*written",
        "suggestion": "Restart data has been written.",
        "file_hint": [".msg", ".sta"],
    },
]


# ── File scanning helpers ────────────────────────────────────────────────

_FILE_EXTENSIONS = [".sta", ".msg", ".dat", ".log"]


def _read_file_tail(path: str, max_lines: int = 500) -> list[str]:
    """Read the last *max_lines* lines of a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return lines[-max_lines:]
    except Exception:
        return []


def _read_file_head(path: str, max_lines: int = 200) -> list[str]:
    """Read the first *max_lines* lines of a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = []
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                lines.append(line)
        return lines
    except Exception:
        return []


def _scan_file(filepath: str, patterns: list[dict]) -> list[DiagnosticEvent]:
    """Scan a single file against all patterns and return matching events."""
    _, ext = os.path.splitext(filepath)
    # Read both head (for syntax/keyword errors) and tail (for convergence)
    lines = _read_file_head(filepath, 200) + _read_file_tail(filepath, 500)
    if not lines:
        return []

    fname = os.path.basename(filepath)
    events: list[DiagnosticEvent] = []

    for pat in patterns:
        file_hint = pat.get("file_hint")
        if file_hint is not None and ext not in file_hint:
            continue
        regexes = pat["regex"]
        if isinstance(regexes, str):
            regexes = [regexes]
        compiled = [re.compile(r, re.IGNORECASE) for r in regexes]

        for lineno, line in enumerate(lines, start=1):
            for rx in compiled:
                if rx.search(line):
                    events.append(DiagnosticEvent(
                        category=pat["category"],
                        severity=pat["severity"],
                        pattern_id=pat["id"],
                        file=fname,
                        line=lineno,
                        raw_line=line.strip(),
                        suggestion=pat["suggestion"],
                    ))
                    break  # one match per pattern per line is enough
    return events


# ── Public API ───────────────────────────────────────────────────────────


def diagnose_logs(job_name: str, workdir: str | None = None) -> DiagnosisReport:
    """Scan all solver output files for a job and return a DiagnosisReport.

    Args:
        job_name: The job name (without extension).
        workdir: The working directory. Defaults to ``os.getcwd()``.

    Returns:
        A ``DiagnosisReport`` containing all matched diagnostic events.
    """
    if workdir is None:
        workdir = os.getcwd()

    report = DiagnosisReport(
        job_name=job_name,
        workdir=workdir,
        files_scanned=[],
    )

    for ext in _FILE_EXTENSIONS:
        filepath = os.path.join(workdir, job_name + ext)
        if os.path.isfile(filepath):
            report.files_scanned.append(os.path.basename(filepath))
            for event in _scan_file(filepath, _PATTERNS):
                report.add_event(event)

    return report


def diagnose_logs_from_paths(
    job_name: str,
    file_paths: list[str],
) -> DiagnosisReport:
    """Scan explicit file paths (instead of constructing from job_name + workdir).

    Useful when the caller knows exactly which files to scan.
    """
    report = DiagnosisReport(
        job_name=job_name,
        workdir="",
        files_scanned=[],
    )

    for filepath in file_paths:
        if os.path.isfile(filepath):
            report.files_scanned.append(os.path.basename(filepath))
            for event in _scan_file(filepath, _PATTERNS):
                report.add_event(event)

    return report


# ── Markdown formatting ──────────────────────────────────────────────────

_CATEGORY_ICONS: dict[str, str] = {
    "license": "🔑",
    "convergence": "🔄",
    "model_setup": "🔧",
    "contact": "🤝",
    "material": "🧱",
    "resources": "💾",
    "environment": "📁",
    "odb": "📦",
    "syntax": "📝",
    "explicit": "⚡",
    "output": "📊",
    "scripting": "🐍",
    "mesh": "🔺",
    "general": "ℹ️",
}

_SEVERITY_MARKERS: dict[str, str] = {
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
}


def format_diagnosis_markdown(report: DiagnosisReport) -> str:
    """Render a DiagnosisReport as a compact, structured Markdown panel."""
    lines: list[str] = []

    # Header
    lines.append(f"## Diagnosis: `{report.job_name}`")
    lines.append("")
    lines.append(f"**Workdir:** `{report.workdir}`")
    lines.append(f"**Files scanned:** {', '.join(report.files_scanned) or '(none found)'}")
    lines.append("")

    # Summary line
    parts = []
    if report.error_count:
        parts.append(f"❌ {report.error_count} error(s)")
    if report.warning_count:
        parts.append(f"⚠️ {report.warning_count} warning(s)")
    if report.info_count:
        parts.append(f"ℹ️ {report.info_count} info")
    if not parts:
        parts.append("✅ No issues detected")
    lines.append(f"**Summary:** {' | '.join(parts)}")
    lines.append("")

    if not report.events:
        lines.append("No diagnostic events found. The solver output appears clean.")
        return "\n".join(lines)

    # Group events by category
    from collections import defaultdict
    grouped: dict[str, list[DiagnosticEvent]] = defaultdict(list)
    for event in report.events:
        grouped[event.category].append(event)

    # Sort categories: errors first, then warnings, then info
    category_order = sorted(
        grouped.keys(),
        key=lambda c: (
            0 if any(e.severity == "error" for e in grouped[c]) else
            1 if any(e.severity == "warning" for e in grouped[c]) else
            2,
            c,
        ),
    )

    for category in category_order:
        events = grouped[category]
        icon = _CATEGORY_ICONS.get(category, "")
        lines.append(f"### {icon} {category.replace('_', ' ').title()}")
        lines.append("")

        # Deduplicate events by pattern_id, keeping the first occurrence
        seen_ids: set[str] = set()
        unique_events: list[DiagnosticEvent] = []
        for e in events:
            if e.pattern_id not in seen_ids:
                seen_ids.add(e.pattern_id)
                unique_events.append(e)

        for e in unique_events:
            marker = _SEVERITY_MARKERS.get(e.severity, "")
            lines.append(f"**{marker} {e.pattern_id}**  ")
            lines.append(f"> {e.suggestion}  ")
            lines.append(f"> *Source: `{e.file}` line {e.line}*")
            lines.append("")
            # Show the raw line as a code block
            lines.append("```")
            lines.append(e.raw_line)
            lines.append("```")
            lines.append("")

    # Footer with quick reference
    lines.append("---")
    lines.append("*Diagnosis generated by abaqus-mcp-pro solver_diagnosis module.*")

    return "\n".join(lines)


def format_diagnosis_compact(report: DiagnosisReport) -> str:
    """Render a compact single-line-per-event version, suitable for CLI."""
    lines: list[str] = []
    lines.append(f"Diagnosis for {report.job_name}:")
    if not report.events:
        lines.append("  No issues detected.")
        return "\n".join(lines)
    for e in report.events:
        marker = _SEVERITY_MARKERS.get(e.severity, "?")
        lines.append(f"  {marker} [{e.category}] {e.pattern_id}: {e.suggestion[:100]}")
    return "\n".join(lines)


# ── Self-contained code snippet for in-Abaqus execution ──────────────────

# This string contains the minimal code needed to run diagnosis inside the
# Abaqus kernel. It is used by server.py's ``diagnose_job`` tool.

DIAGNOSE_IN_ABAQUS_CODE = r'''
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class DiagnosticEvent:
    category: str
    severity: str
    pattern_id: str
    file: str
    line: int
    raw_line: str
    suggestion: str

_PATTERNS = [
    {"id":"license_unavailable","category":"license","severity":"error","regex":[r"License\s+.*not\s+available",r"All\s+licenses\s+are\s+currently\s+in\s+use",r"feature\s+has\s+expired",r"License\s+server\s+.*down",r"cannot\s+connect\s+to\s+license\s+server",r"FLEXnet\s+Licensing\s+error"],"suggestion":"License token is unavailable. Wait for other users to finish, check license server status, or contact your admin.","file_hint":[".log",".msg",".dat"]},
    {"id":"too_many_license_attempts","category":"license","severity":"error","regex":r"Too\s+many\s+attempts\s+to\s+check\s+out","suggestion":"Abaqus retried license checkout too many times. Restart the job, or check if another process is holding the license.","file_hint":[".log",".msg"]},
    {"id":"too_many_attempts","category":"convergence","severity":"error","regex":r"Too\s+many\s+attempts\s+made\s+for\s+this\s+increment","suggestion":"The solver could not converge after repeated cutbacks. Reduce the initial increment size, add stabilization (0.0002), refine the mesh in contact regions, or check for rigid body motion.","file_hint":[".msg",".sta"]},
    {"id":"time_increment_required_too_small","category":"convergence","severity":"error","regex":[r"Time\s+increment\s+required\s+is\s+less\s+than",r"time\s+increment\s+.*below\s+minimum"],"suggestion":"The required time increment fell below the minimum. Reduce the minimum increment size, add contact stabilization, or check for sudden stiffness changes.","file_hint":[".msg",".sta"]},
    {"id":"maximum_increments_exceeded","category":"convergence","severity":"error","regex":r"Maximum\s+number\s+of\s+increments\s+exceeded","suggestion":"The step did not complete within the maximum allowed increments. Increase max increments, reduce load, or use automatic stabilization.","file_hint":[".msg",".sta"]},
    {"id":"too_many_cutbacks","category":"convergence","severity":"warning","regex":r"cut-\s*back|cutback","suggestion":"The solver is repeatedly cutting back the time increment. Check contact, material plasticity, or add automatic stabilization.","file_hint":[".msg",".sta"]},
    {"id":"severe_discontinuity_iterations","category":"convergence","severity":"warning","regex":r"severe\s+discontinuity\s+iterations","suggestion":"Severe discontinuity iterations indicate contact status changes. Check contact pair definitions, adjust penalty stiffness, or use contact stabilization.","file_hint":[".msg",".sta"]},
    {"id":"rigid_body_motion","category":"model_setup","severity":"warning","regex":[r"rigid\s+body\s+mode",r"unconstrained\s+body",r"zero\s+pivot.*node",r"numerical\s+singularity.*node"],"suggestion":"A part is unconstrained and can move freely. Add boundary conditions, tie constraints, or springs to remove rigid body modes.","file_hint":[".msg",".dat"]},
    {"id":"negative_eigenvalues","category":"model_setup","severity":"warning","regex":[r"negative\s+eigenvalue",r"system\s+matrix\s+has\s+\d+\s+negative\s+eigenvalues"],"suggestion":"Negative eigenvalues suggest material instability or buckling. Check for hourglassing, use enhanced hourglass control, refine mesh, or add stabilization.","file_hint":[".msg",".dat"]},
    {"id":"numerical_singularity","category":"model_setup","severity":"warning","regex":r"numerical\s+singularity","suggestion":"Numerical singularity detected at a node. Check BCs, element quality, and material properties.","file_hint":[".msg",".dat"]},
    {"id":"zero_pivot","category":"model_setup","severity":"warning","regex":r"zero\s+pivot","suggestion":"Zero pivot in stiffness matrix. Check for missing BCs, disconnected elements, or incorrect material properties.","file_hint":[".msg",".dat"]},
    {"id":"contact_overclosure","category":"contact","severity":"warning","regex":r"over\s*closure|overclosure","suggestion":"Contact surfaces are penetrating each other initially. Use 'Adjust only to remove overclosure' or adjust the mesh.","file_hint":[".msg",".dat"]},
    {"id":"contact_chattering","category":"contact","severity":"warning","regex":r"chattering","suggestion":"Contact status is changing rapidly. Increase contact stiffness, use softened contact, or refine the mesh in the contact zone.","file_hint":[".msg"]},
    {"id":"contact_pair","category":"contact","severity":"error","regex":r"contact\s+pair.*not\s+found|surface.*not\s+found","suggestion":"A contact pair or surface referenced in the model could not be found. Check that both surfaces exist and are correctly named.","file_hint":[".msg",".dat",".log"]},
    {"id":"material_missing_density","category":"material","severity":"error","regex":[r"density.*must\s+be\s+defined",r"no\s+density.*defined",r"missing\s+mass\s+density"],"suggestion":"Density is required for dynamic/modal/gravity analyses. Add a density to the material definition.","file_hint":[".msg",".dat",".log"]},
    {"id":"material_not_defined","category":"material","severity":"error","regex":[r"material.*not\s+defined",r"material.*not\s+found",r"no\s+material.*assigned"],"suggestion":"A material referenced in the model is not defined. Create the material and assign it to the appropriate section.","file_hint":[".msg",".dat",".log"]},
    {"id":"material_plastic_strain_excessive","category":"material","severity":"warning","regex":r"plastic\s+strain.*exceed|excessive\s+plastic\s+strain","suggestion":"The plastic strain is very large. Check yield stress and hardening data, and that the applied load is realistic.","file_hint":[".msg"]},
    {"id":"material_hyperelastic_unstable","category":"material","severity":"warning","regex":r"hyperelastic.*unstable|Drucker.*stability","suggestion":"The hyperelastic material model may be unstable at the current strain levels.","file_hint":[".msg",".dat"]},
    {"id":"memory_allocation","category":"resources","severity":"error","regex":[r"memory.*exceeded",r"insufficient\s+memory",r"out\s+of\s+memory",r"cannot\s+allocate"],"suggestion":"The job ran out of memory. Reduce mesh density, use fewer CPUs, or increase memory allocation.","file_hint":[".log",".msg",".dat"]},
    {"id":"disk_full","category":"resources","severity":"error","regex":[r"disk\s+full",r"no\s+space\s+left",r"insufficient\s+disk"],"suggestion":"The disk is full. Free up space or redirect output to a different location.","file_hint":[".log",".msg"]},
    {"id":"cpu_count_warning","category":"resources","severity":"info","regex":r"number\s+of\s+cpus|cpu\s+count|parallelization","suggestion":"Check that the CPU count is appropriate for the model size.","file_hint":[".log",".msg"]},
    {"id":"path_too_long","category":"environment","severity":"error","regex":r"path.*too\s+long|file\s+name.*too\s+long","suggestion":"A file path exceeds the OS limit. Move the job to a shorter directory path.","file_hint":[".log",".msg"]},
    {"id":"file_not_found","category":"environment","severity":"error","regex":[r"cannot\s+open\s+file",r"file\s+not\s+found",r"no\s+such\s+file",r"does\s+not\s+exist"],"suggestion":"A required file is missing. Check the file path and working directory.","file_hint":[".log",".msg",".dat"]},
    {"id":"scratch_directory_unavailable","category":"environment","severity":"error","regex":r"scratch.*directory|scratch.*not\s+accessible","suggestion":"The scratch directory is not accessible. Set the scratch environment variable to a valid writable directory.","file_hint":[".log",".msg"]},
    {"id":"lock_file_exists","category":"environment","severity":"error","regex":r"lock\s+file.*exists|already\s+in\s+use","suggestion":"A lock file from a previous run still exists. Remove the .lck file manually.","file_hint":[".log",".msg"]},
    {"id":"odb_upgrade_required","category":"odb","severity":"error","regex":r"odb.*upgrade|odb.*version","suggestion":"The ODB was created by a newer Abaqus version. Use `abaqus upgrade` to convert it.","file_hint":[".log"]},
    {"id":"odb_corrupt","category":"odb","severity":"error","regex":r"odb.*corrupt|odb.*damaged|odb.*cannot\s+be\s+opened","suggestion":"The ODB file appears to be corrupted. Try running `abaqus upgrade` or re-run the analysis.","file_hint":[".log",".msg"]},
    {"id":"odb_no_frames","category":"odb","severity":"warning","regex":r"no\s+frames|odb.*empty","suggestion":"The ODB contains no frames. The analysis may have failed before writing results.","file_hint":[".log"]},
    {"id":"keyword_error","category":"syntax","severity":"error","regex":r"\*\*\*ERROR.*keyword|keyword.*error|unknown\s+keyword","suggestion":"An input file keyword is not recognized. Check for typos and verify the keyword is supported.","file_hint":[".dat",".msg",".log"]},
    {"id":"element_type_unknown","category":"syntax","severity":"error","regex":r"element\s+type.*not\s+recognized|unknown\s+element\s+type","suggestion":"The element type is not valid. Check the Abaqus documentation for valid element type codes.","file_hint":[".dat",".msg"]},
    {"id":"missing_node_set","category":"syntax","severity":"error","regex":r"node\s+set.*not\s+found|nodeset.*not\s+found","suggestion":"A node set referenced in the model does not exist. Create it or correct the name.","file_hint":[".dat",".msg"]},
    {"id":"missing_element_set","category":"syntax","severity":"error","regex":r"element\s+set.*not\s+found|elset.*not\s+found","suggestion":"An element set referenced in the model does not exist. Create it or correct the name.","file_hint":[".dat",".msg"]},
    {"id":"missing_surface","category":"syntax","severity":"error","regex":r"surface.*not\s+found","suggestion":"A surface referenced in the model does not exist. Create it or correct the name.","file_hint":[".dat",".msg"]},
    {"id":"include_file_missing","category":"syntax","severity":"error","regex":r"INCLUDE.*not\s+found|cannot\s+open\s+include","suggestion":"An included file could not be found. Check the file path and working directory.","file_hint":[".dat",".msg",".log"]},
    {"id":"explicit_stable_time_too_small","category":"explicit","severity":"error","regex":[r"stable\s+time\s+increment.*too\s+small",r"time\s+increment.*below.*minimum"],"suggestion":"The stable time increment in explicit is too small. Consider mass scaling or check for very small/distorted elements.","file_hint":[".sta",".msg"]},
    {"id":"excessive_distortion","category":"explicit","severity":"error","regex":r"excessive\s+distortion|element.*distorted","suggestion":"Elements are excessively distorted. Use ALE adaptive meshing, refine the mesh, or reduce the load/velocity.","file_hint":[".msg",".sta"]},
    {"id":"explicit_kinetic_energy_ratio","category":"explicit","severity":"warning","regex":r"kinetic\s+energy.*ratio","suggestion":"The ratio of kinetic to internal energy is high. Slow the loading rate for quasi-static analyses.","file_hint":[".sta"]},
    {"id":"output_variable_invalid","category":"output","severity":"error","regex":r"output\s+variable.*not\s+valid|invalid\s+output","suggestion":"An output variable is not valid for this analysis type. Check the Abaqus output variable list.","file_hint":[".dat",".msg",".log"]},
    {"id":"python_script_error","category":"scripting","severity":"error","regex":[r"Python\s+error",r"Traceback.*most recent call last",r"SyntaxError",r"KeyError",r"AttributeError"],"suggestion":"A Python error occurred during analysis. Check the .log file for the full traceback.","file_hint":[".log"]},
    {"id":"abaqus_command_missing","category":"scripting","severity":"error","regex":r"abaqus.*command\s+not\s+found|abaqus.*not\s+recognized","suggestion":"The abaqus command is not in PATH. Add the Abaqus installation directory to PATH.","file_hint":[".log"]},
    {"id":"mesh_quality_warning","category":"mesh","severity":"warning","regex":r"mesh.*quality|aspect\s+ratio.*exceed|jacobian.*zero","suggestion":"Mesh quality issues. Check for elements with high aspect ratio, small angles, or negative Jacobian.","file_hint":[".dat",".msg",".log"]},
    {"id":"mesh_too_coarse","category":"mesh","severity":"warning","regex":r"mesh.*too\s+coarse|refine\s+mesh","suggestion":"The mesh may be too coarse for accurate results. Consider refining in high-gradient regions.","file_hint":[".msg"]},
    {"id":"analysis_completed","category":"general","severity":"info","regex":r"THE\s+ANALYSIS\s+HAS\s+COMPLETED\s+SUCCESSFULLY|COMPLETED|JOB\s+COMPLETED","suggestion":"The analysis completed successfully.","file_hint":[".log",".msg",".sta"]},
    {"id":"analysis_aborted","category":"general","severity":"error","regex":r"THE\s+ANALYSIS\s+HAS\s+BEEN\s+TERMINATED|ABORTED|JOB\s+ABORTED","suggestion":"The analysis was aborted. Check the error messages above.","file_hint":[".log",".msg",".sta"]},
    {"id":"analysis_interrupted","category":"general","severity":"error","regex":r"ANALYSIS\s+INTERRUPTED|JOB\s+INTERRUPTED","suggestion":"The analysis was interrupted. Check if the system was shut down or the job was manually killed.","file_hint":[".log",".msg"]},
    {"id":"pre_memory_estimate","category":"general","severity":"info","regex":r"memory\s+estimate|estimated\s+memory","suggestion":"Memory estimate for the analysis.","file_hint":[".dat"]},
    {"id":"restart_data_written","category":"general","severity":"info","regex":r"restart\s+data.*written","suggestion":"Restart data has been written.","file_hint":[".msg",".sta"]},
]

def _scan_file(filepath, patterns):
    _, ext = os.path.splitext(filepath)
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        if not lines:
            return []
    except Exception:
        return []
    fname = os.path.basename(filepath)
    events = []
    for pat in patterns:
        file_hint = pat.get("file_hint")
        if file_hint is not None and ext not in file_hint:
            continue
        regexes = pat["regex"]
        if isinstance(regexes, str):
            regexes = [regexes]
        compiled = [re.compile(r, re.IGNORECASE) for r in regexes]
        for lineno, line in enumerate(lines, start=1):
            for rx in compiled:
                if rx.search(line):
                    events.append(DiagnosticEvent(
                        category=pat["category"], severity=pat["severity"],
                        pattern_id=pat["id"], file=fname, line=lineno,
                        raw_line=line.strip(), suggestion=pat["suggestion"]))
                    break
    return events

_JOB_NAME = __JOB_NAME__
_WORKDIR = __WORKDIR__
_FILE_EXTS = [".sta", ".msg", ".dat", ".log"]
report = {"job_name": _JOB_NAME, "workdir": _WORKDIR, "files_scanned": [], "events": [], "error_count": 0, "warning_count": 0, "info_count": 0}
for ext in _FILE_EXTS:
    fp = os.path.join(_WORKDIR, _JOB_NAME + ext)
    if os.path.isfile(fp):
        report["files_scanned"].append(os.path.basename(fp))
        for ev in _scan_file(fp, _PATTERNS):
            report["events"].append({"category": ev.category, "severity": ev.severity, "pattern_id": ev.pattern_id, "file": ev.file, "line": ev.line, "raw_line": ev.raw_line, "suggestion": ev.suggestion})
            if ev.severity == "error":
                report["error_count"] += 1
            elif ev.severity == "warning":
                report["warning_count"] += 1
            else:
                report["info_count"] += 1
result = report
'''


# ── CLI helper ───────────────────────────────────────────────────────────

def diagnose_job_cli(job_name: str, workdir: str | None = None) -> str:
    """Run diagnosis and return formatted Markdown. Intended for CLI use."""
    report = diagnose_logs(job_name, workdir)
    return format_diagnosis_markdown(report)
